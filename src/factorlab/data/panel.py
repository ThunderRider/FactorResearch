"""从 curated 宽表构造研究面板（features ⨝ labels ⨝ 可交易标记）。

这是"数据层 → 门 3"之间缺的那一环。门 3–6 全部以 panel 为输入，
所以 panel 的口径决定了整条研究链的可信度。

用法::

    python -m factorlab.data.panel \\
        --curated data/curated --prefix cn_stock_30m_post \\
        --start 2020-01-01 --end 2026-11-30 \\
        --factors vol_ratio ret_5d ret_20d amihud_lag amt20_lag vol_20d log_amt20 \\
        --out data/panels/panel_all_20200101_20261130_v1.parquet

设计要点：

* **bar 时间戳 = bar 结束时刻**（``14:30`` 代表 14:00–14:30），否则全部时点会错位一格；
* 所有因子只用 ``<= as_of(14:30)`` 的字段（见 ``registry/field_pit.yaml``）；
* ``day_amt`` / ``c1500`` 等含 15:00 的字段一律经 ``lag=1`` 后才进因子；
* 停牌日保留在索引里、值为 NaN；**不填充**；
* ``tradable`` 只是标记，**不删行**（见 docs/01_architecture/data_layer.md §3.4）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from factorlab import labels as L
from factorlab.features import price_volume as pv
from factorlab.features.snapshot import build_snapshot, to_wide
from factorlab.io.store import append_manifest, level_dir

BAR_FIELDS = ["open", "high", "low", "close", "volume", "total_turnover"]
ALL_FACTORS = [
    "vol_ratio", "ret_5d", "ret_20d", "amihud_lag", "amt20_lag",
    "vol_20d", "log_amt20",
]
WINDOW = 20
MIN_PERIODS = 10


# ---------------------------------------------------------------- 读 curated
def load_field_wide(curated_dir: Path, prefix: str, field: str) -> pd.DataFrame:
    """读一个字段的宽表（取匹配到的最新一个文件）。"""
    pattern = f"{prefix}_{field}_*.parquet"
    hits = sorted(curated_dir.glob(pattern))
    if not hits:
        raise FileNotFoundError(f"在 {curated_dir} 找不到 {pattern}")
    df = pd.read_parquet(hits[-1])
    df.index = pd.to_datetime(df.index)
    df.index.name = "datetime"
    df.columns.name = "ticker"
    return df.sort_index()


def wide_fields_to_bars(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """``{字段: 宽表(datetime × ticker)}`` → bar 长表 MultiIndex(order_book_id, datetime)。"""
    parts = []
    for field, wide in fields.items():
        s = wide.stack(future_stack=True).rename(field)
        parts.append(s)
    bars = pd.concat(parts, axis=1)
    bars.index = bars.index.set_names(["datetime", "order_book_id"])
    bars = bars.swaplevel().sort_index()
    bars.index = bars.index.set_names(["order_book_id", "datetime"])
    return bars


# ---------------------------------------------------------------- 快照 → 宽表
def snapshot_wides(snap: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """把快照拆成 ``{字段: 宽表(date × ticker)}``，只保留构造因子需要的那些。"""
    need = ["c1430", "c1500", "c1400", "c1330", "o1000", "c1100", "c1130",
            "v1430", "v1400", "a1430", "day_amt",
            "day_high_upto_1430", "day_low_upto_1430"]
    out = {}
    for field in need:
        if field in snap.columns:
            out[field] = to_wide(snap, field)
    return out


# ---------------------------------------------------------------- 因子
def compute_factors(w: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """由快照宽表算出可注册的因子（名字与 registry/factors.yaml 对齐）。"""
    factors: dict[str, pd.DataFrame] = {}
    c1430 = w.get("c1430")
    c1500 = w.get("c1500")
    day_amt = w.get("day_amt")
    v1430 = w.get("v1430")

    if v1430 is not None:
        factors["vol_ratio"] = pv.vol_ratio(v1430, WINDOW, MIN_PERIODS)
    if c1430 is not None:
        factors["ret_5d"] = pv.ret_nd(c1430, 5)
        factors["ret_20d"] = pv.ret_nd(c1430, 20)

    daily_ret = c1500.pct_change(fill_method=None) if c1500 is not None else None
    if daily_ret is not None and day_amt is not None:
        factors["amihud_lag"] = pv.amihud(daily_ret, day_amt, WINDOW, MIN_PERIODS, lag=1)
        amt20 = pv.amt20_lag(day_amt, WINDOW, MIN_PERIODS, lag=1)
        factors["amt20_lag"] = amt20
        with np.errstate(divide="ignore", invalid="ignore"):
            factors["log_amt20"] = np.log(amt20.replace(0.0, np.nan))
    if daily_ret is not None:
        factors["vol_20d"] = pv.vol_20d(daily_ret, WINDOW, MIN_PERIODS, lag=1)
    return factors


def compute_labels(w: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """由快照宽表算标签（口径见 registry/labels.yaml）。"""
    out = L.build_all(w)
    # 日频辅助标签
    if "c1500" in w:
        out["ret_1d"] = L.ret_nd(w["c1500"], 1)
    return out


# ---------------------------------------------------------------- 面板
def build_panel(
    bars: pd.DataFrame,
    *,
    factors: list[str] | None = None,
    universe: pd.DataFrame | None = None,
    limit_tolerance: float = 0.095,
    min_adt20: float = 5.0e7,
) -> pd.DataFrame:
    """bar 长表 → 研究面板（行 = (date, ticker)）。

    Parameters
    ----------
    bars
        MultiIndex(order_book_id, datetime) 的 bar 数据，需要 ``BAR_FIELDS``。
    factors
        要算的因子子集；``None`` 表示全部可算的。
    universe
        可选 PIT 股票池长表（``date, ticker, pool``）；缺省则面板无 ``pool`` 列。
    """
    snap = build_snapshot(bars)
    w = snapshot_wides(snap)

    fac_all = compute_factors(w)
    lab_all = compute_labels(w)
    want = factors or list(fac_all)
    unknown = [f for f in want if f not in fac_all]
    if unknown:
        raise KeyError(f"无法构造这些因子：{unknown}；可构造 {sorted(fac_all)}")

    series: dict[str, pd.Series] = {}
    for name in want:
        series[name] = fac_all[name].stack(future_stack=True)
    for name, df in lab_all.items():
        series[name] = df.stack(future_stack=True)

    # 可交易标记：day_ret（含截至 14:30 的信息）+ 14:30 的量 + T-1 的 amt20
    if {"c1430", "o1000", "c1500"} <= set(w):
        day_ret = pv.day_ret_from_snapshot(snap)
        dr_w = to_wide(day_ret, "day_ret")
        if "amt20_lag" in fac_all and "v1430" in w:
            tradable = pv.tradable_mask(dr_w, w["v1430"], fac_all["amt20_lag"],
                                        limit_tolerance=limit_tolerance,
                                        min_adt20=min_adt20)
            series["tradable"] = tradable.stack(future_stack=True)

    panel = pd.concat(series, axis=1)
    panel.index = panel.index.set_names(["date", "ticker"])
    panel = panel.sort_index()

    # 全空的行没有意义（停牌/未上市）
    key_cols = [c for c in panel.columns if c != "tradable"]
    panel = panel[panel[key_cols].notna().any(axis=1)]

    out = panel.reset_index()
    if universe is not None and not universe.empty:
        u = universe.copy()
        u["date"] = pd.to_datetime(u["date"])
        out = out.merge(u[["date", "ticker", "pool"]], on=["date", "ticker"], how="left")
        cols = ["date", "ticker", "pool"] + [c for c in out.columns
                                             if c not in ("date", "ticker", "pool")]
        out = out[cols]
    return out


def write_panel(panel: pd.DataFrame, path: str | Path, *,
                dataset: str = "panel", note: str = "ok") -> Path:
    """写 parquet 并登记 MANIFEST（level=panels）。"""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
        if not p.parent.exists():
            p = level_dir("panels") / p.name
    p.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(p, index=False, compression="zstd")
    append_manifest(
        dataset=dataset,
        level="panels",
        path=p,
        start=str(pd.to_datetime(panel["date"]).min().date()),
        end=str(pd.to_datetime(panel["date"]).max().date()),
        n_rows=len(panel),
        n_tickers=int(panel["ticker"].nunique()),
        builder="factorlab.data.panel",
        note=note,
    )
    return p


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="构造研究面板")
    ap.add_argument("--curated", default="data/curated")
    ap.add_argument("--prefix", default="cn_stock_30m_post",
                    help="宽表文件名前缀，如 cn_stock_30m_post / cn_stock_5m_post")
    ap.add_argument("--fields", nargs="+", default=BAR_FIELDS)
    ap.add_argument("--factors", nargs="+", default=None)
    ap.add_argument("--universe", default=None,
                    help="可选：PIT 股票池 parquet（date, ticker, pool）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--note", default="ok")
    args = ap.parse_args(argv)

    curated = Path(args.curated).expanduser()
    if not curated.exists():
        print(f"[error] curated 目录不存在：{curated}", file=sys.stderr)
        return 1

    try:
        fields = {f: load_field_wide(curated, args.prefix, f) for f in args.fields}
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        print("       先按 data/README.md 备好数据，或检查 --prefix。", file=sys.stderr)
        return 1

    shp = {f: v.shape for f, v in fields.items()}
    print(f"读到 {len(fields)} 个字段：{shp}")
    bars = wide_fields_to_bars(fields)
    print(f"bar 长表：{bars.shape}")

    universe = None
    if args.universe:
        up = Path(args.universe)
        if up.exists():
            universe = pd.read_parquet(up)
            print(f"股票池：{len(universe):,} 行")
        else:
            print(f"[warn] 找不到股票池 {up}，面板将没有 pool 列", file=sys.stderr)

    panel = build_panel(bars, factors=args.factors, universe=universe)
    print(f"面板：{panel.shape}，{panel['date'].min().date()} ~ {panel['date'].max().date()}")

    out = args.out or f"panel_{args.prefix.replace('_post', '')}_{len(panel)}.parquet"
    p = write_panel(panel, out, note=args.note)
    print(f"已写出 {p}（MANIFEST 已登记）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
