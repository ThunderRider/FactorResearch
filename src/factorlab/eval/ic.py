"""RankIC、Newey-West t 值、块自举区间。

必报项（见 docs/02_methods/factor_eval.md §9）：
mean_ic / std_ic / icir / **t_naive** / **t_newey_west** / **n_eff** / pos_ratio / n_days

⚠️ naive t 在重叠窗口下会高估 20–30%（旧项目实测 −14.59 vs −11.43）。
   报告里必须两个都给，并把 NW 的那个当结论。
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

MIN_NAMES_PER_DAY = 30
NW_LAG_DEFAULT = 20


# ---------------------------------------------------------------- 逐日 IC
def rank_ic_series(
    panel: pd.DataFrame,
    factor: str,
    label: str,
    *,
    by: tuple[str, ...] = ("date",),
    min_names: int = MIN_NAMES_PER_DAY,
) -> pd.Series:
    """逐组截面 RankIC（Spearman）。

    Parameters
    ----------
    panel
        必须含 ``factor`` / ``label`` 列；``by`` 里的列（默认 ``date``）定义截面。
        **按池分开算 IC 是强制的** —— 选股发生在池内排序，传 ``by=("pool","date")``。
    min_names
        截面股票数少于此值的组不算 IC（小样本噪声会让 IC 序列方差爆炸）。
    """
    for col in (factor, label) + by:
        if col not in panel.columns:
            raise KeyError(f"panel 缺少列 {col!r}")

    d = panel[[*by, factor, label]].dropna()
    if d.empty:
        return pd.Series(dtype=float, name="ic")

    d = d.assign(_rf=d.groupby(list(by), observed=True)[factor].rank(),
                 _rl=d.groupby(list(by), observed=True)[label].rank())
    ic = (d.groupby(list(by), observed=True)
            .apply(lambda g: g["_rf"].corr(g["_rl"]) if len(g) >= min_names else np.nan,
                   include_groups=False)
            .dropna())
    ic.name = "ic"
    return ic


# ---------------------------------------------------------------- t 值
def newey_west_t(series: pd.Series, lag: int = NW_LAG_DEFAULT) -> float:
    """均值的 Newey-West (HAC) t 值。

    ``Var_NW = γ0 + 2 Σ_{j=1..lag} (1 - j/(lag+1)) γj``，
    其中 ``γj = (1/n) Σ (x_t - x̄)(x_{t-j} - x̄)``；``t = x̄ / sqrt(Var_NW / n)``。

    参数 ``lag`` 应取该因子的最大重叠窗口（20 日窗 → lag=20）。
    """
    x = pd.Series(series).dropna().to_numpy(dtype=float)
    n = len(x)
    if n < max(3, lag + 2):
        return float("nan")
    xbar = x.mean()
    dev = x - xbar
    gamma0 = float((dev * dev).mean())
    var = gamma0
    for j in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - j / (lag + 1.0)
        gamma_j = float((dev[j:] * dev[:-j]).mean())
        var += 2.0 * weight * gamma_j
    if var <= 0:
        return float("nan")
    return float(xbar / math.sqrt(var / n))


def bootstrap_mean_ci(
    series: pd.Series,
    *,
    block: int = 20,
    n: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """均值的块自举置信区间（默认 95%）。

    **给 IC 序列用**：区间不含 0 才算显著。块长取 ≈ 最大重叠窗（20），
    因为日度 IC 也有惯性；用 iid 自举会让区间假性收窄。
    """
    x = pd.Series(series).dropna().to_numpy(dtype=float)
    total = len(x)
    if total < max(block * 3, 30):
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(total / block))
    starts = np.arange(total - block + 1)
    means = np.empty(n)
    for i in range(n):
        idx = rng.choice(starts, size=n_blocks, replace=True)
        sample = np.concatenate([x[j: j + block] for j in idx])[:total]
        means[i] = sample.mean()
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return (lo, hi)


def naive_t(series: pd.Series) -> float:
    """``mean/std × sqrt(n)`` —— 仅作对照，不作为结论。"""
    x = pd.Series(series).dropna()
    n = len(x)
    if n < 3 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * math.sqrt(n))


def effective_n(series: pd.Series) -> float:
    """由 lag-1 自相关近似的有效样本数：``n × (1-ρ)/(1+ρ)``。"""
    x = pd.Series(series).dropna()
    if len(x) < 3:
        return float("nan")
    rho = float(x.autocorr(lag=1) or 0.0)
    rho = max(min(rho, 0.99), -0.99)
    return float(len(x) * (1.0 - rho) / (1.0 + rho))


# ---------------------------------------------------------------- 汇总
def ic_summary(
    panel: pd.DataFrame,
    factors: list[str],
    labels: list[str],
    *,
    by: tuple[str, ...] = ("date",),
    min_names: int = MIN_NAMES_PER_DAY,
    nw_lag: int = NW_LAG_DEFAULT,
    group_keys: tuple[str, ...] | None = None,
    bootstrap_n: int = 1000,
    bootstrap_block: int = 20,
) -> pd.DataFrame:
    """因子 × 标签 的 IC 统计表。

    ``group_keys`` 用于把结果按池分行（例如 ``("pool",)``）——
    每一张 IC 表都必须按池分行（见 factor_eval.md §9）。
    """
    rows: list[dict] = []
    keys = group_keys if group_keys is not None else tuple(k for k in by if k not in ("date",))
    if keys:
        for key_vals, sub in panel.groupby(list(keys), observed=True):
            key_vals = key_vals if isinstance(key_vals, tuple) else (key_vals,)
            rows.extend(_one_group(sub, factors, labels, by, min_names, nw_lag,
                                   dict(zip(keys, key_vals)),
                                   bootstrap_n, bootstrap_block))
    else:
        rows.extend(_one_group(panel, factors, labels, by, min_names, nw_lag, {},
                               bootstrap_n, bootstrap_block))
    return pd.DataFrame(rows)


def _one_group(sub: pd.DataFrame, factors: list[str], labels: list[str],
               by: tuple[str, ...], min_names: int, nw_lag: int,
               meta: dict, bootstrap_n: int = 1000,
               bootstrap_block: int = 20) -> list[dict]:
    out: list[dict] = []
    for f in factors:
        if f not in sub.columns:
            continue
        for lab in labels:
            if lab not in sub.columns:
                continue
            s = rank_ic_series(sub, f, lab, by=by, min_names=min_names)
            if s.empty:
                continue
            sd = float(s.std(ddof=1)) if len(s) > 1 else float("nan")
            ci = bootstrap_mean_ci(s, block=bootstrap_block, n=bootstrap_n)
            out.append({
                **meta,
                "factor": f,
                "label": lab,
                "mean_ic": float(s.mean()),
                "std_ic": sd,
                "icir": float(s.mean() / sd) if sd else float("nan"),
                "t_naive": naive_t(s),
                "t_newey_west": newey_west_t(s, lag=nw_lag),
                "n_days": int(len(s)),
                "n_eff": effective_n(s),
                "pos_ratio": float((s > 0).mean()),
                **dict(zip(("ci_lo", "ci_hi"), ci)),
            })
    return out
