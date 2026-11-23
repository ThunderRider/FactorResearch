"""bar 级统计因子：RESI / coef_std。

这两个来自旧项目 V1 线，**都已判 rejected / watch**（见 registry/factors.yaml）：

* ``resi``     IC −0.058，但与 20 日波动率相关 **0.72** → 本质是"买高波动"
* ``coef_std`` IC −0.009 ≈ 0，从未做过消融测试

保留实现是为了让"等价性测试"和"消融测试"可以做（这是它们唯一的用途）。

⚠️ 窗口单位是 **bar 数**，不是天数。40 根 30 分钟 bar ≈ 5 个交易日。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:  # talib 是可选依赖
    import talib

    _HAS_TALIB = True
except Exception:  # pragma: no cover
    talib = None
    _HAS_TALIB = False

BARS_PER_DAY_30M = 8


def _ols_residual_std(y: np.ndarray, window: int) -> np.ndarray:
    """滚动线性回归的残差标准差（不依赖 talib 的纯 numpy 实现）。"""
    n = len(y)
    out = np.full(n, np.nan)
    if n < window:
        return out
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    sxx = ((x - x_mean) ** 2).sum()
    for i in range(window - 1, n):
        seg = y[i - window + 1: i + 1]
        if not np.isfinite(seg).all():
            continue
        beta = ((x - x_mean) * (seg - seg.mean())).sum() / sxx
        alpha = seg.mean() - beta * x_mean
        resid = seg - (alpha + beta * x)
        out[i] = resid.std(ddof=0)
    return out


def resi(bars: pd.DataFrame, window: int = 40, min_periods: int | None = None) -> pd.Series:
    """去趋势残差波动：``ln(典型价)`` 对 ``window`` 根 bar 线性回归，取残差标准差。

    Parameters
    ----------
    bars
        单只股票的 bar（DatetimeIndex）。需要 ``high`` / ``low`` / ``close``。

    Returns
    -------
    与 bars 同索引的 Series，只在 as_of 时点之后的 bar 上有意义
    （调用者需自行取 ``14:30`` 那根）。
    """
    min_periods = min_periods or window
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    lnk = np.log(typical.to_numpy(dtype=float))
    return pd.Series(_ols_residual_std(lnk, window), index=bars.index, name="resi")


def coef_std(bars: pd.DataFrame, window: int = 40) -> pd.Series:
    """量价相关稳定性：``rolling_corr(Δln 价格, Δln 量, window)`` 的滚动标准差。"""
    lnk = np.log((bars["high"] + bars["low"] + bars["close"]) / 3.0)
    lnv = np.log(bars["volume"].replace(0.0, np.nan))
    corr = lnk.diff().rolling(window, min_periods=window).corr(lnv.diff())
    return corr.rolling(window, min_periods=window).std().rename("coef_std")


def slope_norm(bars: pd.DataFrame, window: int = 102) -> pd.Series:
    """归一化趋势 = 回归斜率 / 价格波动（≈ 单位风险的漂移）。用于档位类信号。"""
    lnk = np.log((bars["high"] + bars["low"] + bars["close"]) / 3.0)
    x = np.arange(len(lnk), dtype=float)
    if len(lnk) < window:
        return pd.Series(np.nan, index=bars.index, name="slope_norm")

    slope = lnk.rolling(window, min_periods=window).apply(
        lambda s: np.polyfit(x[: len(s)], s.to_numpy(), 1)[0], raw=False)
    vol = lnk.rolling(window, min_periods=window).std()
    return (slope / vol.replace(0.0, np.nan)).rename("slope_norm")


def bar_index_slope(volume: pd.Series, window_bars: int) -> pd.Series:
    """成交量斜率（档位用）。窗口单位是 **bar 数**，不是天数。

    ⚠️ 不要用自然日做横轴：旧项目实测会让小盘池 23% 的信号翻转，
    V3 净收益从 9.55% 掉到 −1.37%（docs/03_knowledge/lessons_learned.md L10）。
    """
    x = np.arange(len(volume), dtype=float)
    return volume.rolling(window_bars, min_periods=window_bars).apply(
        lambda s: np.polyfit(x[: len(s)], s.to_numpy(), 1)[0], raw=False).rename("slope")


def tier_from_slope(slope: pd.Series, low_mult: float = 1.0 / 16.0) -> pd.Series:
    """斜率 > 0 → 1.0，否则 → low_mult（默认 1/16）。NaN 视为低档。"""
    return pd.Series(
        np.where(slope.fillna(0.0) > 0, 1.0, low_mult), index=slope.index, name="tier")
