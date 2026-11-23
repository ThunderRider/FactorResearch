"""稳健性：块自举、脆弱性曲线、分年统计。

判定线（见 docs/02_methods/portfolio_eval.md）：
* 块自举 95% CI 必须不含 0；报告 ``P(年化 < 0)``
* 脆弱性：剔除最好 **5** 天后净年化仍 > 0
* 分年：至少 3/4 年为正，最差年份 > −10%
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ---------------------------------------------------------------- 基础指标
def perf(daily: pd.Series | np.ndarray, periods: int = TRADING_DAYS) -> dict:
    """年化 / 波动 / Sharpe / MDD / 胜率 / n。"""
    s = pd.Series(daily).dropna()
    n = len(s)
    if n < 2:
        return {"n": n, "ann": np.nan, "vol": np.nan, "sharpe": np.nan,
                "mdd": np.nan, "win": np.nan}
    nav = (1 + s).cumprod()
    ann = float(nav.iloc[-1] ** (periods / n) - 1)
    vol = float(s.std(ddof=1) * np.sqrt(periods))
    return {
        "n": n,
        "ann": ann,
        "vol": vol,
        "sharpe": float(ann / vol) if vol else np.nan,
        "mdd": float((nav / nav.cummax() - 1).min()),
        "win": float((s > 0).mean()),
    }


def max_drawdown_recovery(daily: pd.Series) -> dict:
    """最大回撤 + 恢复天数。

    **恢复时间比回撤幅度更重要**：−20% 但 2 个月恢复，与 −20% 但 10 个月恢复，
    是完全不同的产品（见 portfolio_eval.md §2.2）。
    """
    s = pd.Series(daily).dropna()
    if len(s) < 2:
        return {"mdd": np.nan, "trough": None, "recovery_days": np.nan, "recovered": False}
    nav = (1 + s).cumprod()
    dd = nav / nav.cummax() - 1.0
    trough_idx = dd.idxmin()
    mdd = float(dd.min())

    pos = nav.index.get_indexer([trough_idx])[0] if isinstance(nav.index, pd.Index) else 0
    peak_part = nav.iloc[: pos + 1]
    peak = float(peak_part.max())
    after = nav.iloc[pos:]
    recovered = (after >= peak)
    recovery_days = int(recovered.values.argmax()) if recovered.any() else np.nan
    return {"mdd": mdd, "trough": trough_idx, "recovery_days": recovery_days,
            "recovered": bool(recovered.any())}


# ---------------------------------------------------------------- 脆弱性
def fragility_curve(daily: pd.Series, ks: tuple[int, ...] = (0, 1, 2, 3, 5, 8, 10, 20),
                    periods: int = TRADING_DAYS) -> pd.DataFrame:
    """剔除**最好**的 k 个交易日后，年化与 Sharpe 怎么变。

    k=5 归零 → 结构性脆弱，必须在材料里披露（旧项目 V3 就是这个结果）。
    """
    s = pd.Series(daily).dropna()
    rows = []
    for k in ks:
        keep = s.sort_values(ascending=False).iloc[k:]
        p = perf(keep, periods)
        rows.append({"k": k, **p})
    return pd.DataFrame(rows)


def fragility_at(daily: pd.Series, k: int = 5) -> float:
    """``fragility_curve`` 在 k 处的年化（便捷函数）。"""
    return float(fragility_curve(daily, ks=(k,)).iloc[0]["ann"])


# ---------------------------------------------------------------- 块自举
def block_bootstrap_metrics(
    daily: pd.Series,
    *,
    block: int = 20,
    n: int = 3000,
    seed: int = 0,
    periods: int = TRADING_DAYS,
) -> dict:
    """块自举：给出年化与 Sharpe 的 95% CI，以及 ``P(年化 < 0)``。

    ``block`` 取 ≈ 最大重叠窗（默认 20）。**不要用 iid 自举** ——
    日收益也有惯性，iid 会让区间假性收窄（见 falsified.md 第 14 条）。
    """
    s = pd.Series(daily).dropna().to_numpy(dtype=float)
    total = len(s)
    if total < block * 3:
        return {"ann_lo": np.nan, "ann_hi": np.nan, "sharpe_lo": np.nan,
                "sharpe_hi": np.nan, "p_ann_negative": np.nan, "n_boot": 0}

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(total / block))
    starts = np.arange(total - block + 1)

    anns = np.empty(n)
    srs = np.empty(n)
    for i in range(n):
        idx = rng.choice(starts, size=n_blocks, replace=True)
        sample = np.concatenate([s[j: j + block] for j in idx])[:total]
        p = perf(sample, periods)
        anns[i] = p["ann"]
        srs[i] = p["sharpe"]

    return {
        "ann_lo": float(np.percentile(anns, 2.5)),
        "ann_hi": float(np.percentile(anns, 97.5)),
        "sharpe_lo": float(np.nanpercentile(srs, 2.5)),
        "sharpe_hi": float(np.nanpercentile(srs, 97.5)),
        "p_ann_negative": float((anns < 0).mean()),
        "n_boot": n,
    }


# ---------------------------------------------------------------- 分段
def by_period(daily: pd.Series, freq: str = "YE", periods: int = TRADING_DAYS) -> pd.DataFrame:
    """按年（或月）统计。**必报**：单年驱动 = regime 依赖。"""
    s = pd.Series(daily).dropna()
    if s.empty:
        return pd.DataFrame()
    key = pd.to_datetime(s.index).to_period("Y" if freq.upper().startswith("Y") else "M")
    rows = []
    for label, sub in s.groupby(key):
        p = perf(sub, periods)
        rows.append({"period": str(label), **p})
    return pd.DataFrame(rows)


def concentration(daily: pd.Series, top: int = 10) -> dict:
    """收益集中度：最好 ``top`` 天占全部毛收益的比例。

    ``> 50%`` → 收益极度集中（超短周期策略的固有特征，须披露）。
    旧项目 V1 是 97%，V6 是 53%。
    """
    s = pd.Series(daily).dropna()
    if s.empty or s.sum() == 0:
        return {"top_n": top, "contribution": np.nan}
    return {"top_n": top, "contribution": float(s.nlargest(top).sum() / s.sum())}


def excess_vs_benchmark(
    portfolio: pd.Series,
    benchmark: pd.Series,
    exposure: pd.Series | None = None,
    periods: int = TRADING_DAYS,
) -> dict:
    """对基准的超额（**按组合实际敞口折算**）。

    不折算敞口会让超额虚高 —— 这是最常见的报告错误之一。
    """
    p = pd.Series(portfolio).dropna()
    b = pd.Series(benchmark).reindex(p.index).fillna(0.0)
    w = pd.Series(exposure).reindex(p.index) if exposure is not None else pd.Series(1.0, index=p.index)
    w = w.fillna(0.0)
    excess = p - b * w
    n = len(excess)
    if n < 3:
        return {"excess_ann": np.nan, "ir": np.nan, "t": np.nan, "beta": np.nan}
    ann_ex = float((1 + excess).prod() ** (periods / n) - 1)
    sd = excess.std(ddof=1)
    var_b = b.var(ddof=1)
    beta = float(p.cov(b) / var_b) if var_b else np.nan
    return {
        "excess_ann": ann_ex,
        "ir": float(ann_ex / (sd * np.sqrt(periods))) if sd else np.nan,
        "t": float(excess.mean() / sd * np.sqrt(n)) if sd else np.nan,
        "beta": beta,
    }
