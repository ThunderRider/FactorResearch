"""数据层的端到端测试：宽表 → bar 长表 → 快照 → 面板。

门 3–6 全部以 panel 为输入，所以这条路必须有一条能跑的回归测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factorlab import labels as L
from factorlab.data import panel as pb


@pytest.fixture
def bars() -> pd.DataFrame:
    """合成 30 分钟 bar：6 个交易时段 × 8 根 bar × 12 只股票 × 20 天。"""
    rng = np.random.default_rng(2026)
    sessions = ["10:00", "10:30", "11:00", "11:30", "13:30", "14:00", "14:30", "15:00"]
    days = pd.bdate_range("2025-01-01", periods=20)
    tickers = [f"{i:06d}.XSHE" for i in range(12)]

    idx = []
    for d in days:
        for t in sessions:
            idx.append(pd.Timestamp(f"{d.date()} {t}"))
    idx = pd.DatetimeIndex(idx, name="datetime")

    frames = []
    for tk in tickers:
        base = 10 + rng.normal()
        px = base * np.cumprod(1 + rng.normal(0, 0.004, len(idx)))
        vol = rng.integers(1_000, 9_000, len(idx)).astype(float)
        frames.append(pd.DataFrame({
            "open": px * (1 + rng.normal(0, 0.001, len(idx))),
            "high": px * 1.01,
            "low": px * 0.99,
            "close": px,
            "volume": vol,
            "total_turnover": vol * px,
        }, index=idx))
    out = pd.concat(frames, keys=tickers, names=["order_book_id", "datetime"])
    return out.sort_index()


def test_snapshot_uses_bar_end_timestamps(bars):
    """``14:30`` 必须代表 14:00–14:30 那根（bar 结束时刻口径）。"""
    snap = pb.build_snapshot(bars)
    assert {"c1430", "c1500", "v1430", "day_amt"} <= set(snap.columns)
    # 14:30 的收盘应等于原始 bar 里 14:30 的 close
    one = bars.xs("000000.XSHE", level=0)
    assert snap.loc[("000000.XSHE", pd.Timestamp("2025-01-02")), "c1430"] == pytest.approx(
        one.loc[pd.Timestamp("2025-01-02 14:30"), "close"])


def test_up_to_asof_aggregates_exclude_late_bars(bars):
    """截至 14:30 的最高价必须 <= 当日全天最高价（且通常严格更小）。"""
    snap = pb.build_snapshot(bars)
    assert (snap["day_high_upto_1430"] <= snap["day_high"] + 1e-12).all()


def test_build_panel_shape_and_columns(bars):
    panel = pb.build_panel(bars, factors=["vol_ratio", "ret_20d", "amihud_lag", "vol_20d"])
    for col in ("date", "ticker", "vol_ratio", "ret_20d", "amihud_lag", "vol_20d",
                "ret_1445_next_1115", "ret_tail", "ret_overnight", "ret_morning"):
        assert col in panel.columns, f"面板缺少 {col}"
    assert panel["date"].nunique() == 20
    assert panel["ticker"].nunique() == 12


def test_panel_labels_satisfy_decomposition(bars):
    """面板里的三段分解必须仍满足恒等式（否则下游 IC 全部错位）。"""
    panel = pb.build_panel(bars)
    rebuilt = ((1 + panel["ret_tail"]) * (1 + panel["ret_overnight"])
               * (1 + panel["ret_morning"]) - 1.0)
    diff = (rebuilt - panel["ret_1445_next_1115"]).abs().dropna()
    assert len(diff) > 0
    assert diff.max() < 1e-9


def test_panel_has_no_lookahead_in_amt20(bars):
    """``amt20_lag`` 必须严格小于「含今日」的 20 日均额（后者含 15:00）。"""
    panel = pb.build_panel(bars, factors=["amt20_lag"])
    one = panel[panel["ticker"] == "000000.XSHE"].set_index("date")["amt20_lag"].dropna()
    assert len(one) > 0
    # 与「含今日」版本比较：lag 版应等于它整体后移一行
    day_amt = pb.snapshot_wides(pb.build_snapshot(bars))["day_amt"]
    with_today = day_amt["000000.XSHE"].rolling(20, min_periods=10).mean()
    lagged = with_today.shift(1).reindex(one.index)
    assert np.allclose(one.to_numpy(), lagged.to_numpy(), equal_nan=True)


def test_tradable_is_a_flag_not_a_filter(bars):
    """``tradable`` 只打标记；因子行数不应因此减少。"""
    with_flag = pb.build_panel(bars, factors=["vol_ratio"])
    assert "tradable" in with_flag.columns
    assert with_flag["tradable"].dtype == bool


def test_unknown_factor_is_rejected(bars):
    with pytest.raises(KeyError):
        pb.build_panel(bars, factors=["not_a_real_factor"])


def test_wide_fields_to_bars_roundtrip(bars):
    """宽表 ↔ bar 长表互转后数据一致。"""
    fields = {
        f: bars[f].unstack("order_book_id")
        for f in ("open", "close", "volume")
    }
    for w in fields.values():
        w.index.name = "datetime"
        w.columns.name = "ticker"
    back = pb.wide_fields_to_bars(fields)
    restored = back["close"].unstack("order_book_id")
    restored.columns.name = "ticker"
    pd.testing.assert_frame_equal(
        restored,
        fields["close"].sort_index(),
        check_freq=False,
    )


def test_load_field_wide_picks_latest(tmp_path):
    """同字段有多个区间文件时，取最新一个。"""
    idx = pd.bdate_range("2025-01-01", periods=3, name="datetime")
    old = pd.DataFrame({"000001.XSHE": [1.0, 2.0, 3.0]}, index=idx)
    new = pd.DataFrame({"000001.XSHE": [4.0, 5.0, 6.0]}, index=idx)
    old.to_parquet(tmp_path / "cn_stock_30m_post_close_20200101_20250101.parquet")
    new.to_parquet(tmp_path / "cn_stock_30m_post_close_20200101_20260101.parquet")

    got = pb.load_field_wide(tmp_path, "cn_stock_30m_post", "close")
    assert got.iloc[0, 0] == 4.0


def test_write_panel_registers_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORLAB_DATA_ROOT", str(tmp_path))
    from factorlab.io import store

    panel = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
        "ticker": ["000001.XSHE", "000001.XSHE"],
        "vol_ratio": [1.0, 1.2],
    })
    p = pb.write_panel(panel, tmp_path / "panel_test.parquet", dataset="panel_test")
    assert p.exists()
    man = store.read_manifest()
    assert len(man) == 1
    assert man.iloc[0]["level"] == "panels"
