"""数据质量校验（对应 docs/01_architecture/data_layer.md §6 第 7 步）。

用法::

    python -m factorlab.io.quality --path data/curated/cn_stock_30m_post_close_*.parquet
    python -m factorlab.io.quality --path <p1> <p2> --json

设计原则：**只报告，不修**。修数据是人的决定，脚本只把问题摆出来。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from factorlab.config import load_config
from factorlab.io.store import read_wide


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    severity: str = "error"          # error | warn

    def as_dict(self) -> dict:
        return {"check": self.name, "passed": self.passed,
                "detail": self.detail, "severity": self.severity}


@dataclass
class QualityReport:
    path: str
    n_rows: int = 0
    n_tickers: int = 0
    start: str = ""
    end: str = ""
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity == "error")

    def as_dict(self) -> dict:
        return {
            "path": self.path, "n_rows": self.n_rows, "n_tickers": self.n_tickers,
            "start": self.start, "end": self.end, "passed": self.passed,
            "results": [r.as_dict() for r in self.results],
        }


TICKER_OK = ("XSHE", "XSHG", "INDX", "BJSE")


def check_wide(df: pd.DataFrame, cfg: dict | None = None) -> QualityReport:
    """对一张宽表（date × ticker）做全套校验。"""
    cfg = cfg or load_config("data").get("quality", {})
    min_stocks = int(cfg.get("min_stocks_per_day", 100))
    max_missing = float(cfg.get("max_missing_ratio", 0.30))
    forbid_nonpos = bool(cfg.get("forbid_nonpositive_price", True))

    rep = QualityReport(path="<memory>", n_rows=len(df), n_tickers=df.shape[1])
    if len(df):
        rep.start = df.index.min().strftime("%Y-%m-%d")
        rep.end = df.index.max().strftime("%Y-%m-%d")

    # 1. 索引
    rep.results.append(CheckResult(
        "index_is_datetime",
        isinstance(df.index, pd.DatetimeIndex) and df.index.name == "date",
        f"type={type(df.index).__name__}, name={df.index.name!r}"))
    rep.results.append(CheckResult(
        "index_sorted_unique",
        bool(df.index.is_monotonic_increasing and not df.index.has_duplicates),
        f"monotonic={df.index.is_monotonic_increasing}, "
        f"dupes={int(df.index.duplicated().sum())}"))

    # 2. ticker 格式
    bad = [c for c in df.columns if not str(c).upper().endswith(TICKER_OK)]
    rep.results.append(CheckResult(
        "ticker_format", not bad,
        f"{len(bad)} 个不合规，例：{bad[:3]}" if bad else "ok"))

    # 3. 每日股票数
    per_day = df.notna().sum(axis=1)
    low = per_day[per_day < min_stocks]
    rep.results.append(CheckResult(
        "min_stocks_per_day", len(low) == 0,
        f"{len(low)} 天不足 {min_stocks} 只；最低 {int(per_day.min()) if len(per_day) else 0}",
        severity="error"))

    # 4. 缺失率
    miss = float(df.isna().to_numpy().mean()) if df.size else 0.0
    rep.results.append(CheckResult(
        "missing_ratio", miss <= max_missing,
        f"{miss:.1%}（阈值 {max_missing:.0%}）", severity="warn"))

    # 5. 非正价格
    num = df.select_dtypes(include=[np.number])
    if forbid_nonpos and num.size:
        nonpos = int((num.to_numpy() <= 0).sum())
        rep.results.append(CheckResult(
            "positive_values", nonpos == 0, f"{nonpos} 个 <= 0 的取值"))

    # 6. 单日跳变（后复权下不应出现）
    if num.shape[1] and len(num) > 1:
        ret = num.pct_change(fill_method=None)
        jumps = int((ret.abs() > 0.30).to_numpy().sum())
        rep.results.append(CheckResult(
            "no_extreme_jumps", jumps == 0,
            f"{jumps} 个 |单日涨跌| > 30% 的取值（后复权下应不存在；"
            "若为成交量/成交额字段属正常）", severity="warn"))

    return rep


def check_file(path: str | Path, cfg: dict | None = None) -> QualityReport:
    df = read_wide(path)
    rep = check_wide(df, cfg)
    rep.path = str(path)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="宽表数据质量校验")
    ap.add_argument("--path", nargs="+", required=True, help="parquet 路径，支持通配符")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    paths: list[str] = []
    for pat in args.path:
        hit = glob.glob(pat)
        paths.extend(hit or [pat])

    reports = []
    for p in paths:
        try:
            reports.append(check_file(p))
        except Exception as exc:  # noqa: BLE001
            if args.json:
                reports.append(QualityReport(path=p, results=[
                    CheckResult("load", False, repr(exc))]))
            else:
                print(f"[load-fail] {p}: {exc}")

    if args.json:
        print(json.dumps([r.as_dict() for r in reports], ensure_ascii=False, indent=2))
    else:
        for r in reports:
            flag = "PASS" if r.passed else "FAIL"
            print(f"[{flag}] {r.path}  {r.n_rows:,} 行 × {r.n_tickers} 列  {r.start}~{r.end}")
            for c in r.results:
                mark = "ok  " if c.passed else f"{c.severity.upper():4s}"
                print(f"   - {mark} {c.name:24s} {c.detail}")

    return 0 if all(r.passed for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
