"""因子评估 CLI —— 从面板出发，产出脚本体的一页报告。

用法::

    python -m factorlab.eval.run \\
        --panel  data/panels/panel_mac-min_20200101_20261130_v3.parquet \\
        --factors vol_ratio amihud_lag ret_20d \\
        --label  ret_1445_next_1115 \\
        --out    artifacts/results/20261120-baseline

产出（``--out`` 目录）::

    ic_summary.csv      因子 × (池) 的 IC 统计（含 NW t 与 n_eff）
    decile.csv          分层收益（均值 + 中位数）
    long_short.csv      q_top − q_bottom 的日均 bp 与 t
    coverage.csv        覆盖率与失效期
    report.txt          人读摘要
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from factorlab.config import load_config
from factorlab.eval import decile, ic
from factorlab.eval.stability import by_period


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="因子层评估")
    ap.add_argument("--panel", required=True)
    ap.add_argument("--factors", nargs="+", required=True)
    ap.add_argument("--label", default=None, help="默认取 configs/evals/default.yaml 的 primary")
    ap.add_argument("--out", default="artifacts/results/_adhoc")
    ap.add_argument("--pool-col", default="pool", help="池列名；不存在则不按池分行")
    ap.add_argument("--nq", type=int, default=10)
    ap.add_argument("--min-names", type=int, default=30)
    ap.add_argument("--nw-lag", type=int, default=20)
    return ap.parse_args(argv)


def load_panel(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    df = pd.read_parquet(p)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    if "order_book_id" in df.columns and "ticker" not in df.columns:
        df = df.rename(columns={"order_book_id": "ticker"})
    return df


def coverage_table(panel: pd.DataFrame, factors: list[str],
                   pool_col: str | None = None) -> pd.DataFrame:
    rows = []
    groups = [(None, panel)] if pool_col not in panel.columns else panel.groupby(pool_col)
    for key, sub in groups:
        for f in factors:
            if f not in sub.columns:
                continue
            cov = sub.groupby("date", observed=True)[f].apply(lambda s: s.notna().mean())
            rows.append({
                "pool": key, "factor": f,
                "coverage": float(sub[f].notna().mean()),
                "min_daily_coverage": float(cov.min()) if len(cov) else np.nan,
                "n_days": int(len(cov)),
            })
    return pd.DataFrame(rows)


def build_report(ic_df: pd.DataFrame, dec_df: pd.DataFrame,
                 ls_df: pd.DataFrame, cov_df: pd.DataFrame,
                 label: str) -> str:
    lines = ["=" * 78, f"因子层评估（label = {label}）", "=" * 78, ""]

    if not ic_df.empty:
        lines.append("【IC 统计】naive t 会高估 20–30%，结论看 NW t")
        cols = [c for c in ("pool", "factor", "mean_ic", "t_naive",
                            "t_newey_west", "n_days", "n_eff", "pos_ratio")
                if c in ic_df.columns]
        lines.append(ic_df[cols].to_string(index=False,
                                           float_format=lambda x: f"{x: .4f}"))
        lines.append("")

    if not ls_df.empty:
        lines.append("【多空价差 q_top − q_bottom】盈亏平衡线 = 20bp/日（单边 0.1% × 两腿）")
        show = [c for c in ("pool", "factor", "spread_bp", "t_naive",
                            "t_newey_west", "n_days") if c in ls_df.columns]
        lines.append(ls_df[show].to_string(index=False,
                                           float_format=lambda x: f"{x: .2f}"))
        lines.append("")

    if not dec_df.empty:
        lines.append("【分层（前 3 / 后 3 层）】必须同时看均值与中位数")
        head = dec_df.nsmallest(3, "quantile")
        tail = dec_df.nlargest(3, "quantile")
        for name, part in (("低分位", head), ("高分位", tail)):
            show = [c for c in ("pool", "factor", "quantile", "mean", "median")
                    if c in part.columns]
            lines.append(f"  {name}")
            lines.append(part[show].to_string(index=False,
                                              float_format=lambda x: f"{x: .5f}"))
        lines.append("")

    if not cov_df.empty:
        low = cov_df[cov_df["coverage"] < 0.60]
        lines.append("【覆盖率】< 60% 的因子只能在少数票上用")
        lines.append(cov_df.to_string(index=False, float_format=lambda x: f"{x: .3f}"))
        if not low.empty:
            lines.append(f"  ⚠️ {len(low)} 条覆盖率低于 60%")
        lines.append("")

    lines.append("提示：门 3 通过 ≠ 因子有用。必须继续做门 4（正交化 + 置换重要性）")
    lines.append("     与门 5（组合层：单位敞口日收益 vs 0.200%）。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    cfg = load_config("evals")
    label = args.label or cfg.get("labels", {}).get("primary", "ret_1445_next_1115")

    out = Path(args.out)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)

    panel = load_panel(args.panel)
    factors = [f for f in args.factors if f in panel.columns]
    dropped = sorted(set(args.factors) - set(factors))
    if dropped:
        print(f"[warn] panel 里没有这些因子，已跳过：{dropped}", file=sys.stderr)
    if not factors:
        print("[error] 没有任何可用因子", file=sys.stderr)
        return 1
    if label not in panel.columns:
        print(f"[error] panel 里没有标签 {label!r}", file=sys.stderr)
        return 1

    use_pool = args.pool_col in panel.columns
    group_keys = (args.pool_col,) if use_pool else None
    by = (args.pool_col, "date") if use_pool else ("date",)

    ic_df = ic.ic_summary(panel, factors, [label], by=by,
                          min_names=args.min_names, nw_lag=args.nw_lag,
                          group_keys=group_keys)
    ic_df.to_csv(out / "ic_summary.csv", index=False)

    # 分层与多空
    # 因子相关矩阵（先 rank 再 pearson，避免依赖 scipy）；> 0.7 高度可疑
    corr = panel[factors].rank().corr()
    corr.to_csv(out / "factor_corr.csv")
    high = [(a, b, float(corr.loc[a, b]))
            for i, a in enumerate(factors) for b in factors[i + 1:]
            if abs(float(corr.loc[a, b])) >= 0.7]
    if high:
        print("[warn] 因子间高度相关（|r| >= 0.7，可能互为马甲）：", file=sys.stderr)
        for a, b, r in high:
            print(f"        {a} x {b} = {r:+.2f}", file=sys.stderr)

    dec_rows, ls_rows = [], []
    groups = [(None, panel)] if not use_pool else list(panel.groupby(args.pool_col))
    for key, sub in groups:
        for f in factors:
            dec = decile.quantile_returns(sub, f, label, nq=args.nq, by=("date",),
                                          min_names=args.min_names)
            if not dec.empty:
                dec = dec.assign(pool=key, factor=f)
                dec_rows.append(dec)
            ls = decile.long_short_spread(sub, f, label, nq=args.nq, by=("date",),
                                          min_names=args.min_names)
            ls_rows.append({"pool": key, "factor": f, **ls})
    dec_df = pd.concat(dec_rows, ignore_index=True) if dec_rows else pd.DataFrame()
    ls_df = pd.DataFrame(ls_rows)
    if not dec_df.empty:
        dec_df.to_csv(out / "decile.csv", index=False)
    if not ls_df.empty:
        ls_df.to_csv(out / "long_short.csv", index=False)

    cov_df = coverage_table(panel, factors, args.pool_col if use_pool else None)
    cov_df.to_csv(out / "coverage.csv", index=False)

    text = build_report(ic_df, dec_df, ls_df, cov_df, label)
    (out / "report.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\n产物已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
