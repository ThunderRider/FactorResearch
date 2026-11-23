"""PBO / CSCV —— 检验"选参流程"本身，而不是"信号"。

做法：把样本期切成 S 块，穷举所有 "S/2 块当 IS、S/2 块当 OOS" 的对称组合，
每条路径上用 IS 挑出冠军，看它在 OOS 的排位。

    PBO = 冠军落到后 50% 的概率

判定：**PBO < 0.5**（旧项目的决策器是 56.3% → 等于抛硬币，正式判不通过）。

⚠️ 参数冻结、不选参、不重训的策略可以跳过 PBO，但必须在材料里说明为什么跳过
   （见 docs/02_methods/overfitting_controls.md §3.3）。
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd


def _sharpe(returns: np.ndarray) -> float:
    if returns.size < 2:
        return np.nan
    sd = returns.std(ddof=1)
    return float(returns.mean() / sd) if sd else np.nan


def cscv_pbo(
    returns: pd.DataFrame,
    *,
    n_blocks: int = 10,
    metric: str = "sharpe",
    max_combinations: int | None = 2000,
) -> dict:
    """CSCV 版的 PBO。

    Parameters
    ----------
    returns
        ``index = 时间``，``columns = 候选配置``（每个格子一列）。
        例如：决策器的 11 个变体（IQR5×窗口×阈值 + 纯 V3 + 纯 V1）。
    n_blocks
        块数 S，必须是偶数。
    metric
        ``sharpe`` | ``mean`` | ``ann``

    Returns
    -------
    dict: ``pbo, logit_median, n_paths, n_configs, champion_counts``
    """
    if n_blocks % 2 or n_blocks < 2:
        raise ValueError("n_blocks 必须是 >=2 的偶数")

    d = returns.dropna(how="all")
    n = len(d)
    if n < n_blocks * 2:
        raise ValueError(f"样本太短：{n} 行 < {n_blocks * 2}")

    # 分块
    edges = np.linspace(0, n, n_blocks + 1).astype(int)
    blocks = [d.iloc[edges[i]: edges[i + 1]] for i in range(n_blocks)]

    def _score(frame: pd.DataFrame) -> np.ndarray:
        out = []
        for col in frame.columns:
            x = frame[col].dropna().to_numpy(dtype=float)
            if metric == "sharpe":
                out.append(_sharpe(x))
            elif metric == "mean":
                out.append(float(x.mean()) if x.size else np.nan)
            elif metric == "ann":
                if x.size < 2:
                    out.append(np.nan)
                else:
                    out.append(float((1 + x).prod() ** (252 / x.size) - 1))
            else:
                raise ValueError(f"未知 metric={metric!r}")
        return np.asarray(out, dtype=float)

    half = n_blocks // 2
    combos = list(itertools.combinations(range(n_blocks), half))
    if max_combinations and len(combos) > max_combinations:
        rng = np.random.default_rng(0)
        idx = rng.choice(len(combos), size=max_combinations, replace=False)
        combos = [combos[i] for i in sorted(idx)]

    logits: list[float] = []
    champions: list[int] = []

    for is_idx in combos:
        oos_idx = [i for i in range(n_blocks) if i not in is_idx]
        is_frame = pd.concat([blocks[i] for i in is_idx])
        oos_frame = pd.concat([blocks[i] for i in oos_idx])

        is_scores = _score(is_frame)
        oos_scores = _score(oos_frame)
        if np.all(np.isnan(is_scores)):
            continue

        champ = int(np.nanargmax(is_scores))
        champions.append(champ)

        # 冠军在 OOS 的相对排位 ω ∈ (0,1)；ω < 0.5 表示落到中位数以下
        valid = oos_scores[~np.isnan(oos_scores)]
        if valid.size < 2 or np.isnan(oos_scores[champ]):
            continue
        order = pd.Series(oos_scores).rank(pct=True)
        omega = float(order.iloc[champ])
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        logits.append(math.log(omega / (1 - omega)))

    if not logits:
        return {"pbo": np.nan, "logit_median": np.nan, "n_paths": 0,
                "n_configs": d.shape[1], "champion_counts": {}}

    logits_arr = np.asarray(logits)
    return {
        "pbo": float((logits_arr < 0).mean()),
        "logit_median": float(np.median(logits_arr)),
        "n_paths": int(len(logits_arr)),
        "n_configs": int(d.shape[1]),
        "champion_counts": pd.Series(champions).value_counts().to_dict(),
    }


def format_pbo(res: dict) -> str:
    verdict = "不通过（等于抛硬币）" if res["pbo"] >= 0.5 else "通过"
    return (
        f"PBO = {res['pbo']:.1%}   logit 中位数 = {res['logit_median']:.2f}   "
        f"路径 {res['n_paths']}   候选 {res['n_configs']}   → {verdict}\n"
        f"IS 冠军分布（配置序号: 次数）：{res['champion_counts']}"
    )
