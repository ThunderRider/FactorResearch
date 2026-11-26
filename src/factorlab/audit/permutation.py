"""置换重要性（Permutation Importance）—— 回答"抽掉这个因子，策略还剩多少"。

做法：把某个因子的**截面值**在组内（default ``date × pool``）随机打乱，
保持其余因子、池、日期结构不变，重跑选股与回测，看 Sharpe 下降多少。

    ΔSharpe = SR(基准) − mean(SR(打乱该因子))

判定：**ΔSharpe > 0.10**

⚠️ **必须同时跑"噪声占一槽"的对照**。旧项目的教训（lessons_learned L2）：
   打乱 amihud 让净年化从 +9.6% 掉到 −4.0%（ΔSR 0.98），
   但"噪声占一槽"的对照也掉了 0.67 —— **净信息量只有约 0.31，不是 0.98。**
   不给对照会系统性高估 2–3 倍。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _sharpe(daily: pd.Series) -> float:
    s = pd.Series(daily).dropna()
    if len(s) < 3:
        return float("nan")
    sd = s.std(ddof=1)
    if not sd:
        return float("nan")
    ann = float((1 + s).prod() ** (252 / len(s)) - 1)
    return float(ann / (sd * np.sqrt(252)))


def shuffle_within_groups(
    df: pd.DataFrame,
    col: str,
    by: tuple[str, ...] = ("date", "pool"),
    rng: np.random.Generator | None = None,
) -> pd.Series:
    """在组内随机打乱某一列，返回新 Series（索引对齐）。"""
    rng = rng or np.random.default_rng(0)
    out = df[col].copy()
    for _, idx in df.groupby(list(by), observed=True).groups.items():
        vals = out.loc[idx].to_numpy()
        out.loc[idx] = rng.permutation(vals)
    return out


def permutation_importance(
    panel: pd.DataFrame,
    *,
    factor_z_cols: dict[str, float],
    run_backtest,
    by: tuple[str, ...] = ("date", "pool"),
    n_perm: int = 100,
    seed: int = 0,
    include_noise_control: bool = True,
) -> pd.DataFrame:
    """对每个因子做置换重要性。

    Parameters
    ----------
    panel
        必须含 ``by`` 的列 + ``factor_z_cols`` 的键（**标准化后**的列）。
    factor_z_cols
        ``{列名: 权重}``，权重符号即方向，与 ``portfolio.select.composite`` 一致。
    run_backtest
        回调 ``(panel_with_score) -> pd.Series(daily_net)``。
        由调用者决定怎么选股、怎么算成本 —— 本函数不管组合细节。
    include_noise_control
        是否加"噪声占一槽"的对照（**默认必须为 True**）。

    Returns
    -------
    DataFrame: ``variant, sharpe, delta_sharpe, n_perm, sharpe_std``，基准排第一行。
    """
    from factorlab.portfolio.select import composite

    rng = np.random.default_rng(seed)
    cols = list(factor_z_cols)

    def _score_and_run(frame: pd.DataFrame) -> float:
        scored = composite(frame, factor_z_cols)
        daily = run_backtest(scored)
        return _sharpe(daily)

    rows: list[dict] = []
    base = _score_and_run(panel)
    rows.append({"variant": "base", "sharpe": base, "delta_sharpe": 0.0,
                 "n_perm": 1, "sharpe_std": np.nan})

    for col in cols:
        sims = []
        for _ in range(n_perm):
            frame = panel.copy()
            frame[col] = shuffle_within_groups(frame, col, by=by, rng=rng)
            sims.append(_score_and_run(frame))
        arr = np.asarray(sims, dtype=float)
        rows.append({
            "variant": f"shuffle:{col}",
            "sharpe": float(np.nanmean(arr)),
            "delta_sharpe": float(base - np.nanmean(arr)),
            "n_perm": n_perm,
            "sharpe_std": float(np.nanstd(arr)),
        })

    if include_noise_control and cols:
        from factorlab.portfolio.select import zscore

        # ⚠️ 噪声列必须与因子列同尺度（都按组 z-score + 截尾）。
        #    2026-11-26 修复：此前这里直接塞 N(0,1) 就交给 composite，
        #    而 composite 找的是 ``<col>_z`` —— 会直接 KeyError，
        #    也就是说这段对照一直是死代码，从未真正跑出过数。
        #    修复前后的对照（GTJA191 第一批，base Sharpe -1.588）：
        #      不标准化 -1.4432 ± 0.1014 / 按组标准化 -1.4364 ± 0.0955
        #      → 均值差 0.007（0.07 个标准差），标准化只是把对照的抽样噪声压低 6%。
        #    证据：research/2026-11_gtja191_first_batch/result/pi_noise_compare.csv
        sims = []
        for _ in range(n_perm):
            frame = panel.copy()
            # 用一个与任何因子无关的随机列替换最后一槽
            frame["__noise__"] = rng.standard_normal(len(frame))
            frame = zscore(frame, ["__noise__"], by=by, clip=3.0)
            weights = dict(factor_z_cols)
            last = cols[-1]
            weights.pop(last)
            weights["__noise__"] = factor_z_cols[last]
            scored = composite(frame, weights)
            sims.append(_sharpe(run_backtest(scored)))
        arr = np.asarray(sims, dtype=float)
        rows.append({
            "variant": "noise_control",
            "sharpe": float(np.nanmean(arr)),
            "delta_sharpe": float(base - np.nanmean(arr)),
            "n_perm": n_perm,
            "sharpe_std": float(np.nanstd(arr)),
        })

    return pd.DataFrame(rows)


def net_information(pi: pd.DataFrame) -> pd.DataFrame:
    """扣除噪声对照后的净信息量。

    ``net_delta = delta_sharpe(因子) − delta_sharpe(noise_control)``
    """
    if "noise_control" not in set(pi["variant"]):
        return pi.assign(net_delta_sharpe=np.nan)
    noise = float(pi.loc[pi["variant"] == "noise_control", "delta_sharpe"].iloc[0])
    out = pi.copy()
    out["net_delta_sharpe"] = out["delta_sharpe"] - noise
    return out
