"""DSR（Deflated Sharpe Ratio）—— 惩罚"你试了多少次"。

Bailey & López de Prado。核心：观察到的最大夏普是从 N 次试验里挑出来的**最大值**，
其期望本身偏高。DSR 把这个期望扣掉，再看还剩多少显著性。

    门槛：DSR > 0.95

旧项目的困境（见 docs/02_methods/overfitting_controls.md §2.5）：
因为没记账，``N`` 只能事后清点（≈110），``σ(SR)`` 只能给敏感性网格，
于是 DSR 只能报 **0.51 ~ 0.77** —— 永远无法确定这个夏普有多少是搜索的产物。
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329
TRIALS_PER_YEAR = 252


def psr(daily_returns: pd.Series, sr_benchmark_per_period: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio：``P(SR_hat > SR*)``。

    用日频夏普（per-period），公式中的 T 也是日数，两者频率一致。
    """
    r = pd.Series(daily_returns).dropna()
    n = len(r)
    if n < 3:
        return float("nan")
    sd = r.std(ddof=1)
    if sd == 0:
        return float("nan")
    sr = float(r.mean() / sd)                       # per-period
    skew = float(r.skew())
    kurt = float(r.kurtosis() + 3.0)                # 转成非超额峰度
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if denom <= 0:
        return float("nan")
    z = (sr - sr_benchmark_per_period) * math.sqrt(n - 1) / math.sqrt(denom)
    return float(_N.cdf(z))


def expected_max_sharpe(n_trials: int, sigma_sr: float) -> float:
    """N 次独立试验下"最大夏普"的期望（per-period 单位）。

    ``E[max] ≈ σ × [(1-γ)Φ^{-1}(1-1/N) + γΦ^{-1}(1-1/(N e))]``
    """
    if n_trials <= 1 or sigma_sr <= 0:
        return 0.0
    n = float(n_trials)
    a = _N.inv_cdf(1.0 - 1.0 / n)
    b = _N.inv_cdf(1.0 - 1.0 / (n * math.e))
    return float(sigma_sr * ((1.0 - EULER_GAMMA) * a + EULER_GAMMA * b))


def deflated_sharpe(
    daily_returns: pd.Series,
    *,
    n_trials: int,
    sigma_sr_annual: float | None = None,
    sigma_sr_per_period: float | None = None,
    threshold: float = 0.95,
) -> dict:
    """DSR 及其四个配料。

    Parameters
    ----------
    n_trials
        试验次数 N。来自 ``registry/trials_log.csv`` 的累计（含失败的）。
    sigma_sr_annual / sigma_sr_per_period
        全部试验的年化夏普的横截面标准差。**二选一**。
        没记账时给区间——这本身就是"记账缺失"的证据。

    Returns
    -------
    dict: ``sr_annual, sr_per_period, psr, dsr, pass, n_trials, sigma_sr_annual``
    """
    r = pd.Series(daily_returns).dropna()
    n = len(r)
    if n < 3:
        return {"sr_annual": np.nan, "psr": np.nan, "dsr": np.nan,
                "pass": False, "n_trials": n_trials, "sigma_sr_annual": np.nan}

    sd = r.std(ddof=1)
    sr_pp = float(r.mean() / sd) if sd else float("nan")
    sr_annual = sr_pp * math.sqrt(TRIALS_PER_YEAR)

    if sigma_sr_per_period is None:
        if sigma_sr_annual is None:
            sigma_sr_annual = 0.25           # 哨兵值；必须显式传入真实值
        sigma_sr_per_period = sigma_sr_annual / math.sqrt(TRIALS_PER_YEAR)

    sr0 = expected_max_sharpe(n_trials, sigma_sr_per_period)
    d = psr(r, sr_benchmark_per_period=sr0)
    return {
        "sr_annual": sr_annual,
        "sr_per_period": sr_pp,
        "psr": psr(r, 0.0),
        "dsr": d,
        "pass": bool(d >= threshold) if not np.isnan(d) else False,
        "n_trials": int(n_trials),
        "sigma_sr_annual": float(sigma_sr_annual),
        "threshold": threshold,
    }


def dsr_grid(daily_returns: pd.Series,
             n_trials_grid: tuple[int, ...] = (1, 24, 60, 120, 200),
             sigma_grid: tuple[float, ...] = (0.15, 0.25, 0.35)) -> pd.DataFrame:
    """DSR 敏感性网格 —— 记账缺失时唯一能给的回答。

    旧项目的原表就是这个形状（N×σ → DSR），结论是"不惩罚 0.90，记账后 0.54"。
    """
    rows = []
    for n_trials in n_trials_grid:
        for sigma in sigma_grid:
            d = deflated_sharpe(daily_returns, n_trials=n_trials, sigma_sr_annual=sigma)
            rows.append({"n_trials": n_trials, "sigma_sr": sigma,
                         "psr": d["psr"], "dsr": d["dsr"], "pass": d["pass"]})
    return pd.DataFrame(rows)
