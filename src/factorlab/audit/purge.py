"""Purging / Embargo：样本外边界是否共享了信息？

门 6 的第三件事（见 docs/02_methods/overfitting_controls.md §4）。

任何"扩展窗口"的状态变量都会跨越 IS/OOS 边界：

    disp_pct = disp.expanding(120).apply(...)     # OOS 前 120 天与 IS 共享信息

规则：**禁运长度 >= 该策略用到的最大特征窗。**

旧项目的实测（这是它撤回"样本外 99.1 分位"的原因）：

    切分 2025-06-30 · 禁运 0   → OOS Sharpe 0.969
    切分 2025-06-30 · 禁运 120 → OOS Sharpe **0.492**

用法::

    from factorlab.audit.purge import oos_metrics
    r = oos_metrics(daily_net, split="2025-07-01", embargo_days=120)
    print(r["oos_sharpe"], r["n_oos"])
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factorlab.eval.stability import perf


def split_with_embargo(
    index: pd.Index | pd.Series,
    split: str | pd.Timestamp,
    embargo_days: int = 0,
) -> tuple[pd.Index, pd.Index]:
    """把时间轴切成 (IS, OOS)，并在边界处丢弃 ``embargo_days`` 个观测。

    Parameters
    ----------
    index
        DatetimeIndex（或可被 ``pd.to_datetime`` 转换的序列）。
    split
        OOS 的起点（含）。IS = ``[..., split)``。
    embargo_days
        禁运观测数（**不是自然日**）。按行数丢弃，因为重叠窗口的长度是按行计的。
    """
    idx = pd.DatetimeIndex(pd.to_datetime(index)).sort_values()
    split_ts = pd.Timestamp(split)
    is_side = idx[idx < split_ts]
    oos_side = idx[idx >= split_ts]
    if embargo_days > 0 and len(is_side) > embargo_days:
        is_side = is_side[:-embargo_days]
    if embargo_days > 0 and len(oos_side) > embargo_days:
        oos_side = oos_side[embargo_days:]
    return pd.Index(is_side), pd.Index(oos_side)


def oos_metrics(
    daily: pd.Series,
    *,
    split: str | pd.Timestamp,
    embargo_days: int = 0,
    periods: int = 252,
) -> dict:
    """给定切分点与禁运长度，分别算 IS / OOS 的表现。

    Returns
    -------
    dict: ``is_n, oos_n, is_sharpe, oos_sharpe, oos_ann, embargo_days, split``

    **报告里必须同时给出这三项**：切分日 / 禁运长度 / OOS 有效天数。
    缺一个就不是证据，是措辞。
    """
    s = pd.Series(daily).dropna()
    if s.empty:
        return {"is_n": 0, "oos_n": 0, "is_sharpe": np.nan, "oos_sharpe": np.nan,
                "oos_ann": np.nan, "embargo_days": embargo_days, "split": str(split)}

    is_idx, oos_idx = split_with_embargo(s.index, split, embargo_days)
    is_p = perf(s.reindex(is_idx), periods)
    oos_p = perf(s.reindex(oos_idx), periods)
    return {
        "split": str(pd.Timestamp(split).date()),
        "embargo_days": int(embargo_days),
        "is_n": int(is_p["n"]),
        "oos_n": int(oos_p["n"]),
        "is_sharpe": is_p["sharpe"],
        "oos_sharpe": oos_p["sharpe"],
        "oos_ann": oos_p["ann"],
    }


def embargo_sensitivity(
    daily: pd.Series,
    *,
    split: str | pd.Timestamp,
    embargo_grid: tuple[int, ...] = (0, 20, 60, 120),
    periods: int = 252,
) -> pd.DataFrame:
    """同一切分点、不同禁运长度下的 OOS 表现 —— 门 6 的标准输出。"""
    rows = [oos_metrics(daily, split=split, embargo_days=e, periods=periods)
            for e in embargo_grid]
    out = pd.DataFrame(rows)
    if not out.empty and out["oos_sharpe"].notna().any():
        base = out.loc[out["embargo_days"] == 0, "oos_sharpe"]
        if len(base):
            out["decay_vs_no_embargo"] = out["oos_sharpe"] - float(base.iloc[0])
    return out


def format_report(df: pd.DataFrame, feature_window: int | None = None) -> str:
    """人读摘要 + 判定（禁运后 OOS 是否仍成立）。"""
    if df.empty:
        return "（没有可评估的样本）"
    lines = ["样本外禁运敏感性（禁运长度应 >= 最大特征窗）", ""]
    lines.append(df.to_string(index=False, float_format=lambda x: f"{x: .4f}"))
    lines.append("")
    if feature_window is not None:
        ok = df[df["embargo_days"] >= feature_window]
        if len(ok) and np.isfinite(ok["oos_sharpe"]).any():
            v = float(ok["oos_sharpe"].iloc[-1])
            lines.append(f"最大特征窗 {feature_window} 天 → 对应禁运 {int(ok['embargo_days'].iloc[-1])} 天后 "
                         f"OOS Sharpe = {v:.2f}")
            lines.append("→ " + ("仍为负，样本外结论不成立" if v <= 0 else "仍为正，样本外结论可保留（需注明三项口径）"))
    lines.append("报告里必须写全：切分日 / 禁运长度 / OOS 有效天数。")
    return "\n".join(lines)
