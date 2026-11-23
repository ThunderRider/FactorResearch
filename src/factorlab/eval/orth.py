"""正交化：这个因子是新信息，还是旧暴露换了张皮？

门 4 的第一件事（见 docs/02_methods/research_workflow.md 门 4 与
docs/03_knowledge/lessons_learned.md L3）：

    对控制变量做截面回归，用**残差**重算 IC。

判定线：**正交后 IC 保留率 > 60%**。

旧项目的实测（这是它最可能的尽调漏洞）：

    amihud  原始 IC +0.0103 → 对 log 成交额正交后 **−0.0315（符号翻转）**
                            → 对"额 + 波动 + 反转"正交后净年化 9.59% → 0.52%
    vol_ratio 原始 IC −0.0314 → 对"log 额 + 波动"正交后 −0.0302（**保留 96%**）

用法::

    python -m factorlab.eval.orth \\
        --panel data/panels/panel_*.parquet \\
        --factors amihud_lag vol_ratio \\
        --controls log_amt20 vol_20d ret_20d \\
        --label ret_1445_next_1115
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MIN_NAMES = 30
BP = 1e4


# ---------------------------------------------------------------- 残差
def _residual_one(group: pd.DataFrame, factor: str, controls: list[str]) -> pd.Series:
    """单组截面 OLS 的残差（含截距）。样本不足返回全 NaN。"""
    cols = [factor, *controls]
    sub = group[cols].dropna()
    if len(sub) < max(MIN_NAMES, len(controls) + 2):
        return pd.Series(np.nan, index=group.index)
    y = sub[factor].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(sub)), sub[controls].to_numpy(dtype=float)])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    return pd.Series(resid, index=sub.index)


def orthogonalize(
    panel: pd.DataFrame,
    factor: str,
    controls: list[str],
    *,
    by: tuple[str, ...] = ("date",),
) -> pd.Series:
    """逐组（默认逐日截面）把 ``factor`` 对 ``controls`` 回归，返回残差列。

    残差的含义：**"剔除控制变量之后剩下的那部分因子"**。
    若残差 IC 消失甚至翻转，说明原因子只是控制变量的合成包装。
    """
    for col in (factor, *controls, *by):
        if col not in panel.columns:
            raise KeyError(f"panel 缺少列 {col!r}")

    out = pd.Series(np.nan, index=panel.index, name=f"{factor}__resid")
    for _, idx in panel.groupby(list(by), observed=True).groups.items():
        part = _residual_one(panel.loc[idx], factor, controls)
        out.loc[part.index] = part.to_numpy()
    return out


# ---------------------------------------------------------------- IC 保留率
def ic_retention(
    panel: pd.DataFrame,
    factor: str,
    label: str,
    controls: list[str],
    *,
    by: tuple[str, ...] = ("date",),
    min_names: int = MIN_NAMES,
    nw_lag: int = 20,
) -> dict:
    """原始 IC vs 残差 IC → 保留率与是否符号翻转。

    Returns
    -------
    dict: ``raw_ic, resid_ic, retention, sign_flip, raw_t, resid_t, n_days``

    ``retention`` 定义为 ``resid_ic / raw_ic``（同号时为正）。
    符号翻转时 ``retention`` 为负 —— 这正是旧项目 ``amihud`` 的情形。
    """
    from factorlab.eval.ic import newey_west_t, rank_ic_series

    resid = orthogonalize(panel, factor, controls, by=by)
    work = panel.assign(**{f"{factor}__resid": resid})

    raw = rank_ic_series(work, factor, label, by=by, min_names=min_names)
    res = rank_ic_series(work, f"{factor}__resid", label, by=by, min_names=min_names)

    raw_ic = float(raw.mean()) if len(raw) else float("nan")
    resid_ic = float(res.mean()) if len(res) else float("nan")
    retention = resid_ic / raw_ic if raw_ic not in (0.0,) and not np.isnan(raw_ic) else float("nan")
    return {
        "factor": factor,
        "raw_ic": raw_ic,
        "resid_ic": resid_ic,
        "retention": retention,
        "sign_flip": bool(
            not np.isnan(raw_ic) and not np.isnan(resid_ic)
            and raw_ic != 0.0 and np.sign(raw_ic) != np.sign(resid_ic)
        ),
        "raw_t": newey_west_t(raw, lag=nw_lag) if len(raw) else float("nan"),
        "resid_t": newey_west_t(res, lag=nw_lag) if len(res) else float("nan"),
        "n_days": int(len(raw)),
    }


def retention_report(
    panel: pd.DataFrame,
    factors: list[str],
    label: str,
    controls: list[str],
    *,
    by: tuple[str, ...] = ("date",),
    min_names: int = MIN_NAMES,
    nw_lag: int = 20,
    group_keys: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """多个因子 × （可选）多个池 的保留率表。"""
    rows: list[dict] = []
    keys = group_keys or ()
    if keys:
        for key_vals, sub in panel.groupby(list(keys), observed=True):
            key_vals = key_vals if isinstance(key_vals, tuple) else (key_vals,)
            meta = dict(zip(keys, key_vals))
            for f in factors:
                if f in sub.columns:
                    rows.append({**meta, **ic_retention(sub, f, label, controls,
                                                        by=by, min_names=min_names,
                                                        nw_lag=nw_lag)})
    else:
        for f in factors:
            if f in panel.columns:
                rows.append(ic_retention(panel, f, label, controls,
                                         by=by, min_names=min_names, nw_lag=nw_lag))
    out = pd.DataFrame(rows)
    if not out.empty:
        out["passes"] = out["retention"] >= 0.60
    return out


def format_report(df: pd.DataFrame) -> str:
    """人读摘要 + 判定。"""
    if df.empty:
        return "（没有可评估的因子）"
    lines = [
        "正交化：保留率 = 残差 IC / 原始 IC（判定线 60%；负数 = 符号翻转）",
        "",
        df.to_string(index=False, float_format=lambda x: f"{x: .4f}"),
        "",
    ]
    flips = df[df["sign_flip"]] if "sign_flip" in df.columns else df.iloc[0:0]
    if len(flips):
        names = ", ".join(flips["factor"].tolist())
        lines.append(f"⚠️ 符号翻转：{names}")
        lines.append("   → 不是独立因子。对外必须写成「<控制变量>的综合暴露」，")
        lines.append("     不能在 registry/factors.yaml 里标 independent: true。")
    weak = df[(~df["passes"]) & (~df["sign_flip"])] if "passes" in df.columns else df.iloc[0:0]
    if len(weak):
        lines.append(f"⚠️ 保留率不足 60%：{', '.join(weak['factor'].tolist())}")
    if not len(flips) and not len(weak):
        lines.append("✅ 全部通过：残差仍保留 >60% 的 IC，可视为独立信息。")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="因子正交化与 IC 保留率")
    ap.add_argument("--panel", required=True)
    ap.add_argument("--factors", nargs="+", required=True)
    ap.add_argument("--controls", nargs="+", required=True,
                    help="控制变量（>=3 个，缺一个就等于没做正交）")
    ap.add_argument("--label", default="ret_1445_next_1115")
    ap.add_argument("--pool-col", default="pool")
    ap.add_argument("--out", default="artifacts/results/_adhoc")
    ap.add_argument("--min-names", type=int, default=MIN_NAMES)
    ap.add_argument("--nw-lag", type=int, default=20)
    args = ap.parse_args(argv)

    p = Path(args.panel)
    if not p.is_absolute():
        p = Path.cwd() / p
    panel = pd.read_parquet(p)
    if "date" in panel.columns:
        panel["date"] = pd.to_datetime(panel["date"])
    if "order_book_id" in panel.columns and "ticker" not in panel.columns:
        panel = panel.rename(columns={"order_book_id": "ticker"})

    missing = [f for f in args.factors if f not in panel.columns]
    if missing:
        print(f"[warn] panel 里没有：{missing}", file=sys.stderr)
    factors = [f for f in args.factors if f in panel.columns]
    if not factors:
        print("[error] 没有可用因子", file=sys.stderr)
        return 1
    if args.label not in panel.columns:
        print(f"[error] panel 里没有标签 {args.label!r}", file=sys.stderr)
        return 1
    if len(args.controls) < 3:
        print("[warn] 控制变量少于 3 个：正交化的说服力会显著下降", file=sys.stderr)

    use_pool = args.pool_col in panel.columns
    by = (args.pool_col, "date") if use_pool else ("date",)
    df = retention_report(panel, factors, args.label, args.controls, by=by,
                          min_names=args.min_names, nw_lag=args.nw_lag,
                          group_keys=(args.pool_col,) if use_pool else None)

    out = Path(args.out)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "orth.csv", index=False)

    text = format_report(df)
    (out / "orth.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"\n产物：{out / 'orth.csv'}")
    return 0 if (not df.empty and df["passes"].all()) else 1


if __name__ == "__main__":
    sys.exit(main())
