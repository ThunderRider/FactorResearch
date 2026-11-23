"""试验记账（TRIALS_LOG）—— N 是所有统计推断的分母。

旧项目最终的困境：跑了 3 年，事后才清点出 N≈110，
所以 σ(SR) 算不出来，DSR 只能报 **0.51~0.77** 的区间，
**永远无法确定那个夏普是不是搜索的产物**（见 lessons_learned L13）。

用法::

    from factorlab.audit.trials import log_trial
    log_trial(run_id="20261121-vol_ratio", hypothesis="...", object="vol_ratio",
              params="w20", sample="2020-01~2026-10", metric="mean_ic",
              value=None, n_trials=1, note="开账，先记后跑")
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from factorlab.config import REGISTRY_FILES, REPO_ROOT, load_registry

COLS = [
    "run_id", "date", "phase", "hypothesis", "object", "params", "sample",
    "metric", "value", "passed", "n_trials", "notes", "script", "git_sha",
]


def load_trials() -> pd.DataFrame:
    """读 trials_log.csv（跳过 # 注释行）。"""
    try:
        return load_registry("trials")
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=COLS)


def log_trial(
    *,
    run_id: str,
    hypothesis: str,
    object: str,
    params: str = "",
    sample: str = "",
    metric: str = "",
    value: float | None = None,
    passed: str = "tbd",
    n_trials: int = 1,
    notes: str = "",
    script: str = "",
    phase: str = "M2",
    date: str | None = None,
) -> None:
    """追加一行到 ``registry/trials_log.csv``。

    规则（见 docs/02_methods/overfitting_controls.md §1）：
    * **先记账再跑**：``value=None``、``passed='tbd'`` 也是有意义的记录
    * **失败的也要记**：不记的话 N 会虚低，DSR 会虚高
    """
    path = REPO_ROOT / "registry" / REGISTRY_FILES["trials"]
    row = {
        "run_id": run_id,
        "date": date or datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d"),
        "phase": phase,
        "hypothesis": hypothesis,
        "object": object,
        "params": params,
        "sample": sample,
        "metric": metric,
        "value": "" if value is None else value,
        "passed": passed,
        "n_trials": n_trials,
        "notes": notes,
        "script": script,
        "git_sha": _git_sha(),
    }
    header = not path.exists()
    pd.DataFrame([row], columns=COLS).to_csv(
        path, mode="a", header=header, index=False, encoding="utf-8")


def _git_sha() -> str:
    try:
        import subprocess

        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------- 汇总
def total_n(df: pd.DataFrame | None = None) -> int:
    """累计试验次数 N（用于 DSR）。"""
    d = load_trials() if df is None else df
    if d.empty or "n_trials" not in d.columns:
        return 0
    return int(pd.to_numeric(d["n_trials"], errors="coerce").fillna(0).sum())


def sigma_sr(df: pd.DataFrame | None = None, metric: str = "sharpe") -> float:
    """全部试验的夏普的横截面标准差 σ(SR)。

    这是 DSR 的四个配料之一，也是旧项目**唯一缺失**的那一项 ——
    因为它需要"所有试验的 SR 都记下来"，而不只是最好的那个。
    """
    d = load_trials() if df is None else df
    if d.empty or "metric" not in d.columns:
        return float("nan")
    mask = d["metric"].astype(str).str.lower().str.contains(metric, na=False)
    v = pd.to_numeric(d.loc[mask, "value"], errors="coerce").dropna()
    return float(v.std(ddof=1)) if len(v) > 2 else float("nan")


def summarize(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """按 phase / object 汇总试验次数与通过情况。"""
    d = load_trials() if df is None else df
    if d.empty:
        return pd.DataFrame()
    d = d.copy()
    d["n_trials"] = pd.to_numeric(d["n_trials"], errors="coerce").fillna(0)
    return (d.groupby(["phase", "object"], observed=True)
              .agg(n_trials=("n_trials", "sum"),
                   n_rows=("run_id", "size"),
                   n_fail=("passed", lambda s: int((s == "fail").sum())),
                   n_pass=("passed", lambda s: int((s == "pass").sum())))
              .reset_index()
              .sort_values("n_trials", ascending=False))


def report(df: pd.DataFrame | None = None) -> str:
    """人读的记账摘要。"""
    d = load_trials() if df is None else df
    if d.empty:
        return "trials_log 为空 —— 还没有记录任何试验。"
    n = total_n(d)
    s = sigma_sr(d)
    lines = [
        f"试验记录：{len(d)} 行，可清点 N = {n}",
        f"σ(SR) = {s:.3f}" if not np.isnan(s)
        else "σ(SR) 不可得：metric 里含 sharpe 的记录不足 3 条",
    ]
    if not np.isnan(s):
        lines.append("→ 可以把 DSR 从『估算』变成『读数』")
    else:
        lines.append("→ 仍然只能给 DSR 敏感性网格（这本身就是记账缺失的证据）")
    return "\n".join(lines)
