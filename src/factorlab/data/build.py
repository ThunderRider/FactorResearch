"""取数（RQData）—— 可选依赖。

**其余模块都不依赖本文件**（设计目标：离线也能跑完全部审计，
见 docs/03_knowledge/lessons_learned.md L16）。

用法::

    python -m factorlab.data.build --dataset 30m_stock --start 2020-01-01 --end 2026-11-30
    python -m factorlab.data.build --dataset universe_pit --start 2020-01-01 --end 2026-11-30

落盘：``data/curated/<name>.parquet``（一字段一文件）+ ``data/curated/<dataset>/meta.json``
      + 追加 ``data/MANIFEST.csv``
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from factorlab.config import load_config
from factorlab.io.store import build_name, write_meta, write_wide

# configs/data.yaml 里的 dataset → 取数规格
DATASET_SPECS: dict[str, dict[str, Any]] = {
    "30m_stock": dict(dataset="cn_stock_30m", instrument="stock", freq="30m",
                      rq_freq="30m", adjust="post",
                      fields=["open", "high", "low", "close", "volume", "total_turnover"]),
    "5m_stock": dict(dataset="cn_stock_5m", instrument="stock", freq="5m",
                     rq_freq="5m", adjust="post",
                     fields=["open", "high", "low", "close", "volume", "total_turnover"]),
    "daily_stock": dict(dataset="cn_stock_daily", instrument="stock", freq="1d",
                        rq_freq="1d", adjust="post",
                        fields=["open", "high", "low", "close", "volume",
                                "total_turnover", "turnover_rate", "market_cap"]),
    "index": dict(dataset="cn_index", instrument="index", freq="30m",
                  rq_freq="30m", adjust="post",
                  fields=["open", "high", "low", "close", "volume"]),
}


def _init_rq(verbose: bool = True):
    """初始化 rqdatac。凭证从环境变量读（见 .env.example）。"""
    import os

    try:
        import rqdatac
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "未安装 rqdatac。取数需要：pip install rqdatac 并配置 RQDATA_USERNAME/PASSWORD。\n"
            "（其余模块不依赖它：审计与评估可以完全离线运行。）"
        ) from exc

    user = os.environ.get("RQDATA_USERNAME") or os.environ.get("RQDATA_LICENSE")
    pwd = os.environ.get("RQDATA_PASSWORD") or os.environ.get("RQDATA_KEY")
    uri = os.environ.get("RQDATA_URI")
    if uri:
        rqdatac.init(uri=uri)
    elif user and pwd:
        rqdatac.init(username=user, password=pwd)
    else:
        rqdatac.init()
    if verbose:
        print("[rq] 已初始化")
    return rqdatac


def _universe(rq, as_of: str, kind: str = "all") -> list[str]:
    """股票池。``all`` 用全市场 CS，``pit`` 用当日成分。"""
    if kind == "all":
        ins = rq.all_instruments(type="CS", market="cn", date=as_of)
        return sorted(ins["order_book_id"].tolist())
    raise ValueError(f"未知 kind={kind!r}")


def fetch_wide(rq, codes: list[str], fields: list[str], start: str, end: str,
               *, freq: str, adjust: str, chunk: int = 500,
               progress: bool = True) -> dict[str, pd.DataFrame]:
    """分块取数 → ``{field: wide(date × ticker)}``。"""
    acc: dict[str, list[pd.DataFrame]] = {f: [] for f in fields}
    total = (len(codes) + chunk - 1) // chunk
    for i in range(0, len(codes), chunk):
        part = codes[i: i + chunk]
        if progress:
            print(f"  [{i // chunk + 1}/{total}] {len(part)} 只", flush=True)
        df = rq.get_price(part, start_date=start, end_date=end, frequency=freq,
                          fields=fields, adjust_type=adjust,
                          expect_df=True, skip_suspended=False, market="cn")
        if df is None or df.empty:
            continue
        for f in fields:
            if f in df.columns:
                w = df[f].unstack("order_book_id")
                acc[f].append(w)
    out: dict[str, pd.DataFrame] = {}
    for f, parts in acc.items():
        if not parts:
            continue
        wide = pd.concat(parts, axis=1).sort_index()
        wide.index = pd.to_datetime(wide.index)
        wide.index.name = "date"
        wide.columns.name = "ticker"
        out[f] = wide
    return out


def build(dataset: str, start: str, end: str, *,
          codes: list[str] | None = None, chunk: int = 500,
          refresh: bool = False) -> list[str]:
    """取数并落盘，返回写出的文件路径。"""
    if dataset not in DATASET_SPECS:
        raise SystemExit(f"未知 dataset={dataset!r}，可选 {sorted(DATASET_SPECS)}")
    spec = DATASET_SPECS[dataset]
    rq = _init_rq()

    if codes is None:
        codes = _universe(rq, end)
    print(f"[{dataset}] {len(codes)} 只，{start} ~ {end}，字段 {spec['fields']}")

    wides = fetch_wide(rq, codes, spec["fields"], start, end,
                       freq=spec["rq_freq"], adjust=spec["adjust"], chunk=chunk)

    paths: list[str] = []
    for field, wide in wides.items():
        name = build_name(instrument=spec["instrument"], freq=spec["freq"],
                          adjust=spec["adjust"], field=field,
                          start=start, end=end)
        p = write_wide(wide, "curated", name, dataset=spec["dataset"],
                       builder="factorlab.data.build", note="ok",
                       start=start, end=end)
        paths.append(str(p))
        print(f"  → {p.name}  {wide.shape}")

    write_meta("curated", f"{spec['dataset']}_meta.json", {
        "dataset": spec["dataset"],
        "adjust_type": spec["adjust"],
        "frequency": spec["freq"],
        "start_date": start,
        "end_date": end,
        "fields": spec["fields"],
        "universe_size": len(codes),
        "files": {f: build_name(instrument=spec["instrument"], freq=spec["freq"],
                                adjust=spec["adjust"], field=f, start=start, end=end)
                  for f in wides},
        "source": "rqdatac.get_price",
        "known_issues": [],
        "built_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    })
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="取数（RQData）")
    ap.add_argument("--dataset", required=True, choices=sorted(DATASET_SPECS))
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--chunk", type=int, default=500)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)

    build(args.dataset, args.start, args.end, chunk=args.chunk, refresh=args.refresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
