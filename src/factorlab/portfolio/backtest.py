"""组合构建与回测：权重分配、成本、净值、单位敞口日收益。

**第一原则（见 docs/02_methods/portfolio_eval.md §1）**：
别看年化收益，看 **每单位敞口的日收益** vs 盈亏平衡线 0.200%。

    年化收益 = 选股质量 × 仓位大小 − 成本 × 换手

三个东西混在一个数里；必须拆开。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factorlab.eval.stability import perf

BUDGET = 0.96
MAX_WEIGHT = 0.19
BREAKEVEN_DAILY_PER_UNIT = 0.002     # 单边 0.1% × 两条腿


# ---------------------------------------------------------------- 权重
def allocate(n: int, budget: float, cap: float = MAX_WEIGHT) -> np.ndarray:
    """等权 + 单票上限，超额在组内再分配；全部触顶则留现金。"""
    if n <= 0:
        return np.zeros(0)
    w = np.full(n, budget / n, dtype=float)
    for _ in range(20):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        free = ~over
        if free.sum() == 0:
            break
        w[free] += excess / free.sum()
    return w


def equal_weight(picks: pd.DataFrame, *, by: tuple[str, ...] = ("date", "pool"),
                 budget: float = BUDGET, cap: float = MAX_WEIGHT,
                 weight_col: str = "weight") -> pd.DataFrame:
    """组内等权，带单票上限。"""
    d = picks.copy()

    def _one(g: pd.DataFrame) -> pd.Series:
        return pd.Series(allocate(len(g), budget, cap), index=g.index)

    d[weight_col] = (d.groupby(list(by), observed=True, group_keys=False)
                      .apply(_one, include_groups=False)
                      .reindex(d.index))
    return d


# ---------------------------------------------------------------- 回测
def backtest(
    picks: pd.DataFrame,
    *,
    label: str = "ret_1445_next_1115",
    weight_col: str = "weight",
    cost_one_way: float = 0.0010,
    date_col: str = "date",
) -> pd.DataFrame:
    """逐日组合收益与净值。

    ``cost = 单边 × (今日敞口 + 昨日敞口)`` —— 每日全换手时这是精确的。

    返回列：``exposure, gross, cost, net, nav_gross, nav_net, n_miss, n_picks, per_unit``
    """
    d = picks.copy()
    d["_wr"] = d[weight_col] * d[label]
    d["_miss"] = d[label].isna()

    daily = (d.groupby(date_col, observed=True)
               .agg(exposure=(weight_col, "sum"),
                    gross=("_wr", "sum"),
                    n_miss=("_miss", "sum"),
                    n_picks=(weight_col, "size"))
               .sort_index())

    prev_exposure = daily["exposure"].shift(1).fillna(0.0)
    daily["cost"] = cost_one_way * (daily["exposure"] + prev_exposure)
    daily["net"] = daily["gross"] - daily["cost"]
    daily["nav_gross"] = (1 + daily["gross"]).cumprod()
    daily["nav_net"] = (1 + daily["net"]).cumprod()

    # 每单位敞口的日收益（把选股质量与仓位大小分开）
    exposure_safe = daily["exposure"].replace(0.0, np.nan)
    daily["per_unit"] = daily["gross"] / exposure_safe
    return daily


def per_unit_metrics(daily: pd.DataFrame) -> dict:
    """单位敞口日收益 + 是否过盈亏平衡线。"""
    pu = daily["per_unit"].dropna()
    mean_pu = float(pu.mean()) if len(pu) else np.nan
    return {
        "per_unit_daily": mean_pu,
        "breakeven": BREAKEVEN_DAILY_PER_UNIT,
        "margin": None if np.isnan(mean_pu) else mean_pu - BREAKEVEN_DAILY_PER_UNIT,
        "passes": bool(mean_pu > BREAKEVEN_DAILY_PER_UNIT) if not np.isnan(mean_pu) else False,
        "avg_exposure": float(daily["exposure"].mean()),
        "avg_cost": float(daily["cost"].mean()),
    }


# ---------------------------------------------------------------- 汇总
def summary(daily: pd.DataFrame, cost_levels: tuple[float, ...] = ()) -> dict:
    """组合层一页报告的关键数字（模板见 portfolio_eval.md §9）。"""
    out = {
        "gross": perf(daily["gross"]),
        "net": perf(daily["net"]),
        "per_unit": per_unit_metrics(daily),
        "n_days": int(len(daily)),
        "n_miss_total": int(daily["n_miss"].sum()),
    }
    if cost_levels:
        out["cost_sensitivity"] = {}
        exposure = daily["exposure"]
        prev = exposure.shift(1).fillna(0.0)
        for c in cost_levels:
            net_c = daily["gross"] - c * (exposure + prev)
            out["cost_sensitivity"][f"{c:.4f}"] = perf(net_c)
    return out


def format_summary(s: dict) -> str:
    """把 ``summary()`` 打印成人读的几行。"""
    g, n, pu = s["gross"], s["net"], s["per_unit"]
    lines = [
        f"{'':<14}{'毛':>10}{'净':>10}",
        f"{'年化':<12}{g['ann']:>10.2%}{n['ann']:>10.2%}",
        f"{'Sharpe':<12}{g['sharpe']:>10.2f}{n['sharpe']:>10.2f}",
        f"{'MDD':<12}{g['mdd']:>10.2%}{n['mdd']:>10.2%}",
        f"{'胜率':<12}{g['win']:>10.1%}{n['win']:>10.1%}",
        f"每单位敞口日收益 {pu['per_unit_daily']:.4%} "
        f"（盈亏平衡线 {pu['breakeven']:.3%}，{'PASS' if pu['passes'] else 'FAIL'}）",
        f"日均敞口 {pu['avg_exposure']:.1%}   日均成本 {pu['avg_cost']:.4%}   "
        f"缺失 {s['n_miss_total']} 行   {s['n_days']} 天",
    ]
    return "\n".join(lines)
