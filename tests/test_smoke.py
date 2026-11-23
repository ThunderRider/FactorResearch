"""冒烟测试：用合成数据验证管线与关键公式。

**这些测试的目的不是"覆盖率"，而是"防止有人悄悄把口径改错"。**
每一条对应一处真实踩过的坑（见 docs/03_knowledge/lessons_learned.md）。

    pytest -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factorlab import labels as L
from factorlab.audit import dsr as D
from factorlab.audit import pbo as P
from factorlab.audit.lookahead import check_impact, check_shift_version
from factorlab.eval import decile, ic, stability
from factorlab.features import price_volume as pv
from factorlab.portfolio import backtest, select


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20261120)


@pytest.fixture
def snap_fields(rng) -> dict[str, pd.DataFrame]:
    """构造一组满足不对称关系的价格矩阵，用于验证三段分解恒等式。"""
    n_days, n_tk = 120, 20
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    tickers = [f"{i:06d}.XSHE" for i in range(n_tk)]
    r = pd.DataFrame(rng.normal(0, 0.01, (n_days, n_tk)), index=dates, columns=tickers)
    r.index.name = "date"
    r.columns.name = "ticker"
    base = 10.0 * (1 + r).cumprod()
    return {
        "c1430": base,
        "c1500": base * (1 + rng.normal(0, 0.002, base.shape)),
        "c1100": base * (1 + rng.normal(0, 0.002, base.shape)),
        "c1130": base * (1 + rng.normal(0, 0.002, base.shape)),
        "o1000": base * (1 + rng.normal(0, 0.002, base.shape)),
    }


@pytest.fixture
def panel(rng) -> pd.DataFrame:
    """带 pool 的因子面板：factor 与 label 有强正相关（便于断言 IC 方向）。"""
    n_days, n_tk = 200, 60
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    tickers = [f"{i:06d}.XSHE" for i in range(n_tk)]
    rows = []
    for d in dates:
        for t in tickers[:30]:
            f = rng.normal()
            rows.append({"date": d, "ticker": t, "pool": "mac",
                         "fac": f, "noise": rng.normal(),
                         "label": 0.001 * f + rng.normal(0, 0.005)})
        for t in tickers[30:]:
            f = rng.normal()
            rows.append({"date": d, "ticker": t, "pool": "min",
                         "fac": f, "noise": rng.normal(),
                         "label": 0.001 * f + rng.normal(0, 0.005)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 标签
def test_decomposition_identity(snap_fields):
    """三段分解的乘积必须严格等于主标签（否则"拆开看"就无意义）。"""
    total = L.ret_1445_next_1115(snap_fields)
    parts = L.decompose(snap_fields)
    rebuilt = ((1 + parts["ret_tail"]) * (1 + parts["ret_overnight"])
               * (1 + parts["ret_morning"]) - 1.0)
    diff = (rebuilt - total).abs().to_numpy()
    finite = diff[np.isfinite(diff)]
    assert finite.size > 0
    assert finite.max() < 1e-9


def test_label_is_forward_looking(snap_fields):
    """标签必须"用未来"：最后一行应有值，中间行不依赖当日之后的错误方向。"""
    r = L.ret_1445_next_1115(snap_fields)
    assert r.iloc[-1].isna().all(), "最后一天没有次日行情，标签必须是 NaN"


def test_check_decomposition_helper(snap_fields):
    assert L.check_decomposition(snap_fields)


# ---------------------------------------------------------------- PIT
def test_amihud_shift_applied_after_rolling(rng):
    """``lag`` 必须作用在 rolling 之后（这是 shift/rolling 顺序的经典坑）。"""
    dates = pd.bdate_range("2025-01-01", periods=60)
    cols = ["000001.XSHE"]
    ret = pd.DataFrame(rng.normal(0, 0.01, (60, 1)), index=dates, columns=cols)
    amt = pd.DataFrame(5e8, index=dates, columns=cols)

    with_today = pv.amihud(ret, amt, window=20, min_periods=10, lag=0)
    lagged = pv.amihud(ret, amt, window=20, min_periods=10, lag=1)

    # 滞后版应当等于"含当日版整体后移一行"
    pd.testing.assert_frame_equal(lagged.iloc[1:], with_today.iloc[:-1].set_axis(lagged.index[1:]))


def test_check_shift_version_detects_wrong_version(rng):
    """B 检查必须能识别出"用了含今日版本"的字段。"""
    dates = pd.bdate_range("2025-01-01", periods=40)
    v = pd.Series(np.arange(40, dtype=float), index=dates)
    v_lag = v.shift(1)

    ok = check_shift_version(v_lag, v, v_lag)
    bad = check_shift_version(v, v, v_lag)

    assert ok.passed is True
    assert bad.passed is False
    assert "含今日" in bad.detail


def test_impact_threshold():
    """修正跌幅 < 0.5pp 通过；> 1pp 必须报 error（旧项目 amt20 是 −1.66pp）。"""
    assert check_impact(0.0959, 0.0793).passed is False
    assert check_impact(0.1000, 0.0996).passed is True


# ---------------------------------------------------------------- IC
def test_rank_ic_detects_signal(panel):
    s = ic.rank_ic_series(panel, "fac", "label", by=("date",))
    assert s.mean() > 0.15, f"信号 IC 应显著为正，实际 {s.mean():.4f}"

    s_noise = ic.rank_ic_series(panel, "noise", "label", by=("date",))
    assert abs(s_noise.mean()) < 0.1


def test_newey_west_penalises_autocorrelation(rng):
    """自相关序列上 NW t 必须小于 naive t（naive 会高估）。"""
    n = 600
    eps = rng.normal(0, 0.02, n)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.85 * x[i - 1] + eps[i]          # AR(1)，强自相关
    # 先去掉实现均值再加一个正的常数，保证 mean > 0（否则 t 的符号会翻转，比较无意义）
    x = pd.Series(x - x.mean() + 0.004)

    t_naive = ic.naive_t(x)
    t_nw = ic.newey_west_t(x, lag=20)
    assert t_naive > 0
    assert abs(t_nw) < abs(t_naive)
    assert ic.effective_n(x) < len(x) * 0.5


def test_ic_summary_splits_by_pool(panel):
    """每张 IC 表都必须按池分行（混池会把池间差异当信号）。"""
    out = ic.ic_summary(panel, ["fac"], ["label"], by=("pool", "date"),
                        group_keys=("pool",))
    assert set(out["pool"]) == {"mac", "min"}
    assert set(out.columns) >= {"mean_ic", "t_naive", "t_newey_west", "n_eff"}


# ---------------------------------------------------------------- 分层
def test_decile_is_monotone_on_strong_signal(panel):
    dec = decile.quantile_returns(panel, "fac", "label", nq=10, by=("date",))
    rho = decile.monotonicity(dec)
    assert rho > 0.8, f"强信号的分层应单调，实际 ρ={rho:.2f}"


def test_long_short_spread_positive(panel):
    ls = decile.long_short_spread(panel, "fac", "label", nq=10, by=("date",))
    assert ls["spread_bp"] > 0
    assert ls["n_days"] > 100


# ---------------------------------------------------------------- 组合
def test_allocate_respects_cap():
    w = backtest.allocate(6, budget=0.96, cap=0.19)
    assert np.isclose(w.sum(), 0.96)
    assert w.max() <= 0.19 + 1e-12


def test_allocate_keeps_cash_when_all_capped():
    """n 太少导致全部触顶时，应留现金而不是突破上限（旧项目 allocate 的行为）。"""
    w = backtest.allocate(3, budget=0.96, cap=0.19)
    assert w.max() <= 0.19 + 1e-12
    assert w.sum() < 0.96


def test_zscore_and_composite_direction(rng):
    dates = pd.bdate_range("2025-01-01", periods=30)
    df = pd.DataFrame({
        "date": np.repeat(dates, 50),
        "pool": "mac",
        "a": rng.normal(size=30 * 50),
        "b": rng.normal(size=30 * 50),
    })
    z = select.zscore(df, ["a", "b"], by=("date", "pool"))
    assert np.nanmax(np.abs(z["a_z"])) <= 3.0 + 1e-12

    score = select.composite(z, {"a": +1.0, "b": -1.0})["score"]
    manual = (z["a_z"].fillna(0) - z["b_z"].fillna(0)) / 2.0
    np.testing.assert_allclose(score.to_numpy(), manual.to_numpy(), atol=1e-12)


def test_top_n_picks_exactly_n():
    df = pd.DataFrame({
        "date": pd.Timestamp("2025-01-02"),
        "pool": "mac",
        "ticker": [f"{i:06d}.XSHE" for i in range(10)],
        "score": np.arange(10, dtype=float),
        "tradable": True,
    })
    picks = select.top_n(df, n=4)
    assert len(picks) == 4
    assert set(picks["ticker"]) == {f"{i:06d}.XSHE" for i in range(6, 10)}


def test_backtest_cost_formula():
    """日成本 = 单边 × (今日敞口 + 昨日敞口)。"""
    dates = pd.bdate_range("2025-01-01", periods=3)
    picks = pd.DataFrame({
        "date": np.repeat(dates, 2),
        "ticker": ["a", "b"] * 3,
        "weight": [0.5, 0.5] * 3,
        "label": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
    })
    daily = backtest.backtest(picks, label="label", cost_one_way=0.001)
    # 第 0 天：今日 1.0 + 昨日 0 → 0.1%
    assert np.isclose(daily["cost"].iloc[0], 0.001)
    # 第 1 天：今日 1.0 + 昨日 1.0 → 0.2%
    assert np.isclose(daily["cost"].iloc[1], 0.002)
    # 暴露的"每单位敞口日收益"必须与 gross/exposure 一致
    assert np.isclose(daily["per_unit"].iloc[1], daily["gross"].iloc[1] / 1.0)


def test_per_unit_breakeven_flag():
    dates = pd.bdate_range("2025-01-01", periods=5)
    picks = pd.DataFrame({
        "date": dates, "ticker": "a", "weight": 1.0,
        "label": [0.001] * 5,          # 10bp/日，低于 20bp 盈亏线
    })
    daily = backtest.backtest(picks, label="label")
    m = backtest.per_unit_metrics(daily)
    assert m["passes"] is False


# ---------------------------------------------------------------- 稳健性
def test_fragility_curve_decreases(rng):
    """剔除最好的日子后，年化必须单调下降。"""
    daily = pd.Series(rng.normal(0.001, 0.01, 500))
    frag = stability.fragility_curve(daily, ks=(0, 1, 5, 10))
    assert frag["ann"].is_monotonic_decreasing


def test_block_bootstrap_interval_contains_point(rng):
    daily = pd.Series(rng.normal(0.001, 0.01, 500))
    point = stability.perf(daily)["ann"]
    ci = stability.block_bootstrap_metrics(daily, block=20, n=300, seed=0)
    assert ci["ann_lo"] <= point <= ci["ann_hi"]


def test_concentration_detects_extreme_day():
    daily = pd.Series([0.0] * 99 + [0.05])
    assert stability.concentration(daily, top=1)["contribution"] == pytest.approx(1.0)


def test_excess_discounts_by_exposure(rng):
    """超额必须按敞口折算；不折算会虚高。"""
    idx = pd.bdate_range("2025-01-01", periods=100)
    bench = pd.Series(rng.normal(0.001, 0.01, 100), index=idx)
    port = bench * 0.5          # 组合就是半仓的基准
    full = stability.excess_vs_benchmark(port, bench)
    adj = stability.excess_vs_benchmark(port, bench, exposure=pd.Series(0.5, index=idx))
    assert full["excess_ann"] < adj["excess_ann"]


# ---------------------------------------------------------------- 审计
def test_dsr_decreases_with_more_trials(rng):
    """N 越大，DSR 越小 —— 这就是"惩罚你试了多少次"。"""
    daily = pd.Series(rng.normal(0.0008, 0.01, 750))
    d1 = D.deflated_sharpe(daily, n_trials=1, sigma_sr_annual=0.25)["dsr"]
    d120 = D.deflated_sharpe(daily, n_trials=120, sigma_sr_annual=0.25)["dsr"]
    assert d120 < d1


def test_psr_matches_unpenalised_case(rng):
    """N=1 时不惩罚，DSR 应等于 PSR。"""
    daily = pd.Series(rng.normal(0.001, 0.01, 750))
    r = D.deflated_sharpe(daily, n_trials=1, sigma_sr_annual=0.25)
    assert r["dsr"] == pytest.approx(r["psr"], abs=1e-9)


def test_pbo_high_on_pure_noise(rng):
    """纯噪声的配置集：PBO 应该接近 50%（选参没意义）。"""
    rets = pd.DataFrame(rng.normal(0, 0.01, (600, 8)))
    res = P.cscv_pbo(rets, n_blocks=10, max_combinations=200)
    assert 0.2 <= res["pbo"] <= 0.8, f"噪声集 PBO={res['pbo']:.2%} 偏离 50% 太远"


def test_pbo_low_when_one_config_dominates(rng):
    """一个配置显著更优时，PBO 应很低（选参可信）。"""
    rets = pd.DataFrame(rng.normal(0.0005, 0.01, (600, 6)))
    rets[0] = rng.normal(0.004, 0.01, 600)          # 明显更好
    res = P.cscv_pbo(rets, n_blocks=10, max_combinations=200)
    assert res["pbo"] < 0.2, f"强配置下 PBO={res['pbo']:.2%} 应很低"


# ---------------------------------------------------------------- 数据层
def test_wide_roundtrip_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORLAB_DATA_ROOT", str(tmp_path))
    from factorlab.io import store

    dates = pd.bdate_range("2025-01-01", periods=5)
    df = pd.DataFrame(np.arange(10, dtype=float).reshape(5, 2),
                      index=dates, columns=["000001.XSHE", "600000.XSHG"])
    df.index.name = "date"

    name = store.build_name(field="close", start="20250101", end="20250107")
    path = store.write_wide(df, "curated", name, dataset="cn_stock_daily")

    assert path.exists()
    back = store.read_wide(path)
    pd.testing.assert_frame_equal(back, df, check_freq=False)

    man = store.read_manifest()
    assert len(man) == 1
    assert man.iloc[0]["dataset"] == "cn_stock_daily"
    assert str(man.iloc[0]["hash"]).startswith("sha256:")


def test_write_wide_rejects_bad_index(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORLAB_DATA_ROOT", str(tmp_path))
    from factorlab.io import store

    df = pd.DataFrame({"000001.XSHE": [1.0, 2.0]})   # 默认 RangeIndex
    with pytest.raises(ValueError):
        store.write_wide(df, "curated", "x.parquet")


def test_quality_flags_bad_ticker(rng):
    from factorlab.io import quality

    dates = pd.bdate_range("2025-01-01", periods=200)
    df = pd.DataFrame(rng.uniform(10, 20, (200, 3)), index=dates,
                      columns=["000001.XSHE", "600000.XSHG", "BADCODE"])
    df.index.name = "date"
    rep = quality.check_wide(df)
    names = {r.name: r for r in rep.results}
    assert names["ticker_format"].passed is False


# ---------------------------------------------------------------- 注册表
def test_registry_loads_and_is_consistent():
    from factorlab.config import active_factor_ids, load_registry

    reg = load_registry("factors")
    assert len(reg["factors"]) >= 10
    assert "vol_ratio" in active_factor_ids()
    # active 的因子必须有退役条件
    for f in reg["factors"]:
        if f.get("status") == "active":
            assert f.get("retire_if"), f"{f['id']} 缺 retire_if"


def test_field_pit_covers_active_factors():
    from factorlab.config import load_registry

    pit = set(load_registry("field_pit").get("fields", {}))
    for f in load_registry("factors").get("factors", []):
        for fld in f.get("pit_fields", []) or []:
            assert fld in pit, f"{f['id']} 引用了未登记的字段 {fld}"


def test_trials_log_parses():
    from factorlab.audit import trials

    df = trials.load_trials()
    assert not df.empty
    assert trials.total_n(df) >= 100, "迁移的旧项目 N 应 >= 100"
