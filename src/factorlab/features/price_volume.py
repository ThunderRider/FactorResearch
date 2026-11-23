"""量价因子（宽表 in → 宽表 out；每次只算一个因子）。

与 registry/factors.yaml 的 ``id`` 一一对应。所有函数：

* 输入：``DataFrame(date × ticker)`` 或快照 ``MultiIndex(order_book_id, date)``
* 输出：同形状
* **不做标准化**（标准化属于合成阶段，见 ``portfolio.select``）
* **不做 PIT 修正**：调用者必须自己保证输入列已符合 as_of 约定
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 20
DEFAULT_MIN_PERIODS = 10


# ---------------------------------------------------------------- 工具
def _by_ticker(df: pd.DataFrame, fn) -> pd.DataFrame:
    """对宽表按列（每只股票）应用 fn。fn: Series -> Series。"""
    return df.apply(fn, axis=0)


def _rolling(series: pd.Series, window: int, min_periods: int, how: str) -> pd.Series:
    r = series.rolling(window, min_periods=min_periods)
    return getattr(r, how)()


# ---------------------------------------------------------------- 因子
def vol_ratio(v_at_asof: pd.DataFrame, window: int = DEFAULT_WINDOW,
              min_periods: int = DEFAULT_MIN_PERIODS) -> pd.DataFrame:
    """同时刻量比 = v1430 / 过去 N 日同时点均量。

    **必须传同一时点的量**（如 ``v1430``），不要传全天量 ——
    否则会把日内 U 型季节性混进信号。
    方向：**越小越好**（缩量 = 冷门）。
    """
    ma = _by_ticker(v_at_asof, lambda s: _rolling(s, window, min_periods, "mean"))
    return (v_at_asof / ma.replace(0.0, np.nan)).astype(float)


def ret_nd(price_at_asof: pd.DataFrame, n: int) -> pd.DataFrame:
    """N 日动量/反转 = ``p / p.shift(n) - 1``。

    ``n=20`` → ``ret_20d``（方向：越小越好，超跌）。
    注意 ``price_at_asof`` 必须是 as_of 时点价（如 ``c1430``），不是收盘价。
    """
    return _by_ticker(price_at_asof, lambda s: s / s.shift(n) - 1.0).astype(float)


def amihud(daily_ret: pd.DataFrame, day_amt: pd.DataFrame,
           window: int = DEFAULT_WINDOW, min_periods: int = DEFAULT_MIN_PERIODS,
           lag: int = 1) -> pd.DataFrame:
    """Amihud 非流动性 = rolling_mean(|r| / amt)，默认 **lag 1**（PIT 安全）。

    ⚠️ ``daily_ret`` 与 ``day_amt`` 都含当日 15:00 的信息，
    所以 ``lag`` 必须 >= 1。``lag=0`` 只用于对照，不得进因子。

    方向：**越大越好**（越冷门）。
    独立性：❌ 对 log 成交额 / 波动 / 反转正交后 IC 符号翻转 —— 它是合成暴露，
    必须在 ``registry/factors.yaml`` 里标 ``independent: false``。
    """
    if lag < 0:
        raise ValueError("lag 不能为负")
    abs_ret = daily_ret.abs()
    illiq = abs_ret / day_amt.replace(0.0, np.nan)
    out = _by_ticker(illiq, lambda s: _rolling(s, window, min_periods, "mean"))
    if lag:
        out = _by_ticker(out, lambda s: s.shift(lag))
    return out.astype(float)


def updown_5d(volume: pd.DataFrame, close: pd.DataFrame,
              window: int = 5, min_periods: int = 3) -> pd.DataFrame:
    """5 日放量涨跌比（对数）= log((放量上涨量 + 1) / (放量下跌量 + 1)) 的滚动均值。"""
    dclose = close.diff()
    up = volume.where(dclose > 0, 0.0)
    dn = volume.where(dclose < 0, 0.0)

    s_up = up.rolling(window, min_periods=min_periods).sum()
    s_dn = dn.rolling(window, min_periods=min_periods).sum()
    return np.log((s_up + 1.0) / (s_dn + 1.0)).astype(float)


def amt20_lag(day_amt: pd.DataFrame, window: int = DEFAULT_WINDOW,
              min_periods: int = DEFAULT_MIN_PERIODS, lag: int = 1) -> pd.DataFrame:
    """20 日均成交额（默认 T-1 口径）—— 流动性门槛用这个，**不要**用含当日的版本。

    ⚠️ 旧项目在这里翻车过：含当日 15:00 的 amt20 造成 1.66pp 的虚高。
    ``shift`` 必须加在 ``rolling`` **之后**。
    """
    ma = _by_ticker(day_amt, lambda s: _rolling(s, window, min_periods, "mean"))
    if lag:
        ma = _by_ticker(ma, lambda s: s.shift(lag))
    return ma.astype(float)


def vol_20d(daily_ret: pd.DataFrame, window: int = DEFAULT_WINDOW,
            min_periods: int = DEFAULT_MIN_PERIODS, lag: int = 1) -> pd.DataFrame:
    """20 日波动率（默认 T-1 口径）。主要作为正交化的控制变量。"""
    sd = _by_ticker(daily_ret, lambda s: _rolling(s, window, min_periods, "std"))
    if lag:
        sd = _by_ticker(sd, lambda s: s.shift(lag))
    return sd.astype(float)


def day_ret_from_snapshot(snap: pd.DataFrame) -> pd.DataFrame:
    """由快照构造"截至 14:30 的当日涨跌"，用于可交易过滤。

    ``day_ret = (1 + gap) * (1 + intraday) - 1``，其中
    ``gap = o1000 / c1500.shift(1) - 1``、``intraday = c1430 / o1000 - 1``。

    ⚠️ 用 ``c1500.shift(1)``（**昨日**收盘）是安全的；
    ``intraday`` 用当日 ``c1430`` 也是安全的。整体 <= as_of。
    """
    gap = snap["o1000"] / snap.groupby(level=0)["c1500"].shift(1) - 1.0
    intraday = snap["c1430"] / snap["o1000"] - 1.0
    # 返回单列 DataFrame：便于 to_wide 与 tradable_mask 直接使用
    return ((1 + gap) * (1 + intraday) - 1.0).rename("day_ret").to_frame("day_ret")


def tradable_mask(day_ret: pd.DataFrame, v1430: pd.DataFrame,
                  amt20_lagged: pd.DataFrame, *,
                  limit_tolerance: float = 0.095,
                  min_adt20: float = 5.0e7) -> pd.DataFrame:
    """可交易标记（布尔宽表）。**因子层只打标记，不删行**（见 data_layer.md §3.4）。"""
    return ((day_ret.abs() < limit_tolerance)
            & (v1430 > 0)
            & (amt20_lagged > min_adt20)).fillna(False)
