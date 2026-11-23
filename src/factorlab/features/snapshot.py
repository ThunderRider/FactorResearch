"""行情快照：30 分钟 bar → 每日快照（截至 14:30 的时点字段）。

与旧项目 ``wpqc/eval_wpqc_factors.py::build_snapshot`` 口径一致，
命名沿用 ``<字段首字母><HHMM>``（``c1430`` = 14:30 那根 bar 的收盘）。

⚠️ 关键口径：**bar 的时间戳是 bar 的结束时刻**。``14:30:00`` 代表 14:00–14:30。
   见 docs/01_architecture/conventions.md §1。

输入约定（长表，单只股票也可）::

    index = MultiIndex(order_book_id, datetime)  或  列 order_book_id + datetime
    columns = open, high, low, close, volume, total_turnover

输出：``DataFrame(index=(order_book_id, date), columns=<快照字段>)``，全部 <= as_of(T)。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 需要取值的时点 → [(源字段, 目标列名)]
SNAPSHOT_SPEC: dict[str, list[tuple[str, str]]] = {
    "10:00:00": [("open", "o1000")],
    "11:00:00": [("close", "c1100")],
    "11:30:00": [("close", "c1130")],
    "13:30:00": [("close", "c1330")],
    "14:00:00": [("close", "c1400"), ("volume", "v1400")],
    "14:30:00": [("close", "c1430"), ("volume", "v1430"),
                 ("total_turnover", "a1430")],
    # 15:00 是**当日收盘**：晚于 as_of，进因子前必须 shift(1)（见 field_pit.yaml），
    # 但标签构造与可交易判定需要它，所以快照里保留。
    "15:00:00": [("close", "c1500")],
}

# 只包含 <= as_of 的 bar 的聚合（PIT 安全）
AGG_UPTO_ASOF: dict[str, tuple[str, str]] = {
    "day_high_upto_1430": ("high", "max"),
    "day_low_upto_1430": ("low", "min"),
}

# 全部 bar 的聚合（⚠️ 含 14:30–15:00，属于未来信息）
AGG_FULL_DAY: dict[str, tuple[str, str]] = {
    "day_high": ("high", "max"),
    "day_low": ("low", "min"),
    "day_vol": ("volume", "sum"),
    "day_amt": ("total_turnover", "sum"),
}

AS_OF = "14:30:00"


def _as_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """把可能的 MultiIndex 输入统一成 列 order_book_id + datetime。"""
    if isinstance(bars.index, pd.MultiIndex):
        names = list(bars.index.names)
        if len(names) < 2:
            raise ValueError(f"MultiIndex 需要两级，实际 {names}")
        code_level, dt_level = names[0], names[1]
        out = bars.reset_index()
        out = out.rename(columns={code_level: "order_book_id", dt_level: "datetime"})
    else:
        out = bars.copy()
        for col in ("order_book_id", "datetime"):
            if col not in out.columns:
                raise ValueError(f"需要列 {col!r}")
    out["datetime"] = pd.to_datetime(out["datetime"])
    out["order_book_id"] = out["order_book_id"].astype(str)
    return out


def build_snapshot(bars: pd.DataFrame, include_full_day: bool = True) -> pd.DataFrame:
    """把 bar 压成每日快照。

    Parameters
    ----------
    include_full_day
        True 时同时输出 ``day_high`` / ``day_low`` / ``day_vol`` / ``day_amt``。
        ⚠️ 这些字段**含 14:30 之后**的信息，用前必须 ``shift(1)``
        （见 registry/field_pit.yaml）。
    """
    out = _as_frame(bars)
    out["date"] = out["datetime"].dt.normalize()
    out["tod"] = out["datetime"].dt.strftime("%H:%M:%S")

    cols: dict[str, pd.Series] = {}
    for tod, spec in SNAPSHOT_SPEC.items():
        mask = out["tod"] == tod
        sub = out.loc[mask, ["order_book_id", "date"]]
        for src, dst in spec:
            if src in out.columns:
                cols[dst] = pd.Series(out.loc[mask, src].to_numpy(), index=pd.MultiIndex.from_frame(sub))
            else:
                cols[dst] = pd.Series(np.nan, index=pd.MultiIndex.from_frame(sub))
    snap = pd.DataFrame(cols)

    grp = [out["order_book_id"], out["date"]]

    # PIT 安全：只用 <= as_of 的 bar
    upto = out[out["tod"] <= AS_OF]
    g_upto = [upto["order_book_id"], upto["date"]]
    for name, (src, how) in AGG_UPTO_ASOF.items():
        if src in upto.columns:
            agg = upto.groupby(g_upto)[src].agg(how)
            agg.index = agg.index.set_names(["order_book_id", "date"])
            snap[name] = agg

    if include_full_day:
        for name, (src, how) in AGG_FULL_DAY.items():
            if src in out.columns:
                agg = out.groupby(grp)[src].agg(how)
                agg.index = agg.index.set_names(["order_book_id", "date"])
                snap[name] = agg

    snap.index = snap.index.set_names(["order_book_id", "date"])
    return snap.sort_index()


def to_wide(snap: pd.DataFrame, field: str) -> pd.DataFrame:
    """快照 → 宽表（date × ticker）。"""
    wide = snap[field].unstack("order_book_id")
    wide.index.name = "date"
    wide.columns.name = "ticker"
    return wide.sort_index()
