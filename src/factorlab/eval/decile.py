"""分层收益（decile）。

必报：q1..qN 的 **均值与中位数**、q10−q1 的日均 bp。
⚠️ 分层必须控制市场状态（仓位档 / 波动区间），否则会掉进辛普森悖论
   （见 docs/02_methods/factor_eval.md §4.3）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_NAMES_PER_DAY = 30
BP = 1e4


def assign_quantiles(
    panel: pd.DataFrame,
    factor: str,
    *,
    nq: int = 10,
    by: tuple[str, ...] = ("date",),
    min_names: int = MIN_NAMES_PER_DAY,
) -> pd.Series:
    """按组内排名切分位（1..nq）。截面不足 ``min_names`` 的组返回 NaN。"""
    d = panel[[*by, factor]]
    ranks = d.groupby(list(by), observed=True)[factor].rank(method="first")
    sizes = d.groupby(list(by), observed=True)[factor].transform("size")
    q = np.ceil(ranks / sizes * nq).clip(1, nq)
    q[sizes < min_names] = np.nan
    return q.astype("float").rename("quantile")


def quantile_returns(
    panel: pd.DataFrame,
    factor: str,
    label: str,
    *,
    nq: int = 10,
    by: tuple[str, ...] = ("date",),
    min_names: int = MIN_NAMES_PER_DAY,
) -> pd.DataFrame:
    """每个分位的日均/中位收益。

    Returns
    -------
    DataFrame with columns ``quantile, mean, median, count, mean_bp``
    """
    d = panel[[*by, factor, label]].dropna(subset=[factor, label]).copy()
    if d.empty:
        return pd.DataFrame(columns=["quantile", "mean", "median", "count", "mean_bp"])
    d["quantile"] = assign_quantiles(d, factor, nq=nq, by=by, min_names=min_names)
    d = d.dropna(subset=["quantile"])

    # 先算每日每分位的截面均值，再对时间取均值 —— 避免"票多的日子权重大"
    daily = (d.groupby([*by, "quantile"], observed=True)[label]
               .agg(["mean", "median", "size"]).reset_index())
    out = (daily.groupby("quantile", observed=True)
                .agg(mean=("mean", "mean"),
                     median=("median", "median"),
                     count=("size", "mean"),
                     n_days=("mean", "size"))
                .reset_index())
    out["mean_bp"] = out["mean"] * BP
    return out


def long_short_spread(
    panel: pd.DataFrame,
    factor: str,
    label: str,
    *,
    nq: int = 10,
    by: tuple[str, ...] = ("date",),
    min_names: int = MIN_NAMES_PER_DAY,
) -> dict:
    """q_top − q_bottom 的日均价差（bp）与 t 值。

    ``t`` 用逐日价差序列算（naive），并附 Newey-West 版本。
    判定参考：盈亏平衡线是每单位敞口 20bp/日（单边 0.1% × 两条腿）。
    """
    from factorlab.eval.ic import naive_t, newey_west_t

    d = panel[[*by, factor, label]].dropna(subset=[factor, label]).copy()
    if d.empty:
        return {"spread_bp": np.nan, "t_naive": np.nan, "t_newey_west": np.nan, "n_days": 0}
    d["quantile"] = assign_quantiles(d, factor, nq=nq, by=by, min_names=min_names)
    d = d.dropna(subset=["quantile"])

    daily = (d.groupby([*by, "quantile"], observed=True)[label].mean()
               .unstack("quantile"))
    if 1 not in daily.columns or float(nq) not in daily.columns:
        return {"spread_bp": np.nan, "t_naive": np.nan, "t_newey_west": np.nan, "n_days": 0}
    spread = (daily[float(nq)] - daily[1.0]).dropna()
    return {
        "spread_bp": float(spread.mean() * BP),
        "t_naive": naive_t(spread),
        "t_newey_west": newey_west_t(spread),
        "n_days": int(len(spread)),
    }


def monotonicity(dec: pd.DataFrame) -> float:
    """分层单调性：分位序号与收益的 Spearman 相关（−1..1）。

    |ρ| > 0.8 视为单调；接近 0 但有尾部效应 → 只在极端段有效。
    """
    if len(dec) < 3:
        return float("nan")
    # 手算 Spearman，避免引入 scipy 依赖
    a = dec["quantile"].rank()
    b = dec["mean"].rank()
    return float(a.corr(b))
