"""选股：z-score 合成 + 分组取前 N。

与旧项目 V3 口径一致（见 registry/factors.yaml 的 evidence）：

    score = (−z_vol + z_amihud − z_ret) / 3
    池内 z-score、截尾 ±3、每池取前 4

⚠️ 三因子等权的理由不是"算出来的最优"，而是**没有证据支持更高权重**。
   按 PI 调权 = 样本内再优化（见 docs/03_knowledge/factor_eval §6）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_CLIP = 3.0


# ---------------------------------------------------------------- 标准化
def zscore(
    panel: pd.DataFrame,
    cols: list[str],
    *,
    by: tuple[str, ...] = ("date",),
    clip: float = DEFAULT_CLIP,
    suffix: str = "_z",
) -> pd.DataFrame:
    """按组截面标准化并截尾 ±clip。NaN 保持 NaN（不减权、不填 0）。"""
    out = panel.copy()
    g = out.groupby(list(by), observed=True)
    for c in cols:
        mean = g[c].transform("mean")
        std = g[c].transform(lambda s: s.std(ddof=0))
        z = (out[c] - mean) / std.replace(0.0, np.nan)
        out[c + suffix] = z.clip(-clip, clip)
    return out


# ---------------------------------------------------------------- 合成
def composite(panel: pd.DataFrame, weights: dict[str, float],
              *, suffix: str = "_z", out_col: str = "score") -> pd.DataFrame:
    """加权合成。``weights`` 是 ``{因子列名(不含 _z): 权重}``，权重符号即方向。

    >>> composite(panel, {"vol_ratio": -1/3, "amihud_lag": +1/3, "ret_20d": -1/3})
    """
    out = panel.copy()
    score = pd.Series(0.0, index=out.index)
    total_w = 0.0
    for col, w in weights.items():
        col_z = col if col.endswith(suffix) else col + suffix
        if col_z not in out.columns:
            raise KeyError(f"缺少标准化列 {col_z}，先调用 zscore()")
        score = score.add(out[col_z].fillna(0.0) * w, fill_value=0.0)
        total_w += abs(w)
    if total_w:
        score = score / total_w
    out[out_col] = score
    return out


# ---------------------------------------------------------------- 选股
def top_n(
    panel: pd.DataFrame,
    *,
    score_col: str = "score",
    n: int = 4,
    by: tuple[str, ...] = ("date", "pool"),
    eligible: str | None = "tradable",
) -> pd.DataFrame:
    """每组取分数最高的 n 只，返回被选中的行（带 ``rank``）。

    ``eligible``：布尔列名（如 ``tradable``）；若存在则先过滤。
    **并列处理固定为 ``method='first'``** —— 旧项目离线复现与生产差 0.17pp 就是并列处理不同。
    """
    d = panel.copy()
    if eligible and eligible in d.columns:
        d = d[d[eligible].fillna(False)]
    d = d.dropna(subset=[score_col])
    if d.empty:
        return d

    d["rank"] = (d.groupby(list(by), observed=True)[score_col]
                  .rank(method="first", ascending=False))
    return d[d["rank"] <= n].copy()


def selection_overlap(picks: pd.DataFrame, by: tuple[str, ...] = ("date", "pool"),
                      id_col: str = "ticker") -> pd.Series:
    """相邻两日持仓重合率。旧项目 V3 ≈ 44%（日换手 56%）。"""
    sets = picks.groupby(list(by), observed=True)[id_col].apply(set)
    if "pool" in by:
        sets = sets.groupby(level="pool").shift(1).dropna()
        cur = picks.groupby(list(by), observed=True)[id_col].apply(set)
        cur = cur.loc[sets.index]
        return pd.Series([len(c & p) / len(p) if p else np.nan for c, p in zip(cur, sets)],
                         index=sets.index, name="overlap")
    prev = sets.shift(1).dropna()
    cur = sets.loc[prev.index]
    return pd.Series([len(c & p) / len(p) if p else np.nan for c, p in zip(cur, prev)],
                     index=prev.index, name="overlap")
