"""IO 层：宽表/长表读写、MANIFEST 追加、meta 读写、形状转换。

规范见 docs/01_architecture/data_layer.md；形状选择见 ADR 0002。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from factorlab.config import REPO_ROOT, data_root, ensure_dir

TZ = timezone.utc  # manifest 时间戳统一带时区

MANIFEST_COLS = [
    "dataset", "level", "path", "start", "end", "n_rows", "n_tickers",
    "built_at", "builder", "git_sha", "snapshot", "hash", "note",
]

LEVEL_DIRS = {
    "raw": "raw",
    "curated": "curated",
    "features": "features",
    "labels": "labels",
    "panels": "panels",
}


# ---------------------------------------------------------------- 命名
def build_name(
    domain: str = "cn",
    instrument: str = "stock",
    freq: str = "30m",
    adjust: str = "post",
    field: str = "close",
    start: str = "20200101",
    end: str = "20261130",
    version: str | None = None,
    ext: str = "parquet",
) -> str:
    """``<domain>_<instrument>_<freq>_<adjust>_<field>_<start>_<end>[_vN].<ext>``

    例：``cn_stock_30m_post_close_20200101_20261130.parquet``
    """
    start, end = start.replace("-", ""), end.replace("-", "")
    base = f"{domain}_{instrument}_{freq}_{adjust}_{field}_{start}_{end}"
    if version:
        base = f"{base}_{version}"
    return f"{base}.{ext}"


def level_dir(level: str) -> Path:
    if level not in LEVEL_DIRS:
        raise KeyError(f"未知 level={level!r}，可选 {list(LEVEL_DIRS)}")
    return ensure_dir(data_root() / LEVEL_DIRS[level])


# ---------------------------------------------------------------- 宽表
def write_wide(
    df: pd.DataFrame,
    level: str,
    name: str,
    *,
    dataset: str = "",
    builder: str = "",
    snapshot: str | None = None,
    note: str = "ok",
    start: str | None = None,
    end: str | None = None,
    compress: str = "zstd",
) -> Path:
    """写宽表（``date × ticker``）并追加 MANIFEST。

    硬约束：DatetimeIndex、``index.name == 'date'``、升序、无重复。
    """
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.name != "date":
        raise ValueError("宽表必须用 DatetimeIndex 且 index.name == 'date'")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("宽表索引必须升序且无重复")

    path = level_dir(level) / name
    df.to_parquet(path, index=True, compression=compress)

    start = start or df.index.min().strftime("%Y-%m-%d")
    end = end or df.index.max().strftime("%Y-%m-%d")
    append_manifest(
        dataset=dataset or name.split("_")[0],
        level=level,
        path=path,
        start=start,
        end=end,
        n_rows=len(df),
        n_tickers=df.shape[1],
        builder=builder,
        snapshot=snapshot,
        note=note,
    )
    return path


def read_wide(path: str | Path, columns: Iterable[str] | None = None) -> pd.DataFrame:
    p = Path(path)
    if not p.is_absolute():
        p = data_root() / p
    df = pd.read_parquet(p, columns=list(columns) if columns else None)
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df.sort_index()


# ---------------------------------------------------------------- 长表
def wide_to_long(df: pd.DataFrame, key: str, key_value: str) -> pd.DataFrame:
    """宽表 → 长表 ``date,ticker,<key>,value``。

    ``key`` 是列名（``factor`` / ``label``），``key_value`` 是该列填的值
    （因子 id / 标签 id）。例如把收盘价宽表转成 features 长表：

    >>> wide_to_long(close_wide, key="factor", key_value="c1430")
    """
    out = df.reset_index().melt(id_vars="date", var_name="ticker", value_name="value")
    out["date"] = pd.to_datetime(out["date"])
    out = out.dropna(subset=["value"]).copy()
    out[key] = key_value
    return (out[["date", "ticker", key, "value"]]
            .sort_values(["date", "ticker"]).reset_index(drop=True))


def long_to_wide(df: pd.DataFrame, key: str, key_value: str) -> pd.DataFrame:
    """长表 → 宽表（一次只取一个 key 值）。

    >>> long_to_wide(feat_long, key="factor", key_value="vol_ratio")
    """
    if key not in df.columns:
        raise ValueError(f"长表缺少列 {key!r}")
    sub = df[df[key] == key_value]
    wide = sub.pivot_table(index="date", columns="ticker", values="value", aggfunc="first")
    wide.index = pd.to_datetime(wide.index)
    wide.index.name = "date"
    wide.columns.name = "ticker"
    return wide.sort_index()


def write_long(
    df: pd.DataFrame,
    level: str,
    name: str,
    *,
    key: str = "factor",
    dataset: str = "",
    builder: str = "",
    snapshot: str | None = None,
    note: str = "ok",
) -> Path:
    """写长表 ``date,ticker,<key>,value``（列顺序固定）。"""
    for col in ("date", "ticker", key, "value"):
        if col not in df.columns:
            raise ValueError(f"长表缺少列 {col!r}")
    path = level_dir(level) / name
    out = df[["date", "ticker", key, "value"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out[key] = out[key].astype(str)
    out["ticker"] = out["ticker"].astype(str)
    out.to_parquet(path, index=False, compression="snappy")
    append_manifest(
        dataset=dataset or name.split("_")[0],
        level=level,
        path=path,
        start=out["date"].min().strftime("%Y-%m-%d"),
        end=out["date"].max().strftime("%Y-%m-%d"),
        n_rows=len(out),
        n_tickers=out["ticker"].nunique(),
        builder=builder,
        snapshot=snapshot,
        note=note,
    )
    return path


def read_long(path: str | Path, key: str = "factor",
              values: list[str] | None = None) -> pd.DataFrame:
    p = Path(path)
    if not p.is_absolute():
        p = data_root() / p
    df = pd.read_parquet(p, filters=[(key, "in", values)] if values else None)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------- MANIFEST
def manifest_path() -> Path:
    return data_root() / "MANIFEST.csv"


def append_manifest(
    *,
    dataset: str,
    level: str,
    path: Path,
    start: str,
    end: str,
    n_rows: int,
    n_tickers: int,
    builder: str = "",
    git_sha: str = "",
    snapshot: str | None = None,
    note: str = "ok",
) -> None:
    """追加一行到 ``data/MANIFEST.csv``；文件不存在则写表头。"""
    p = Path(path)
    try:
        rel = str(p.relative_to(data_root()))
    except ValueError:
        rel = str(p)
    row = {
        "dataset": dataset,
        "level": level,
        "path": rel,
        "start": start,
        "end": end,
        "n_rows": n_rows,
        "n_tickers": n_tickers,
        "built_at": datetime.now(TZ).astimezone().isoformat(timespec="seconds"),
        "builder": builder,
        "git_sha": git_sha or _git_sha(),
        "snapshot": snapshot or "",
        "hash": f"sha256:{sha16(p)}",
        "note": note,
    }
    mp = manifest_path()
    header = not mp.exists()
    pd.DataFrame([row], columns=MANIFEST_COLS).to_csv(
        mp, mode="a", header=header, index=False, encoding="utf-8")


def read_manifest() -> pd.DataFrame:
    mp = manifest_path()
    if not mp.exists():
        return pd.DataFrame(columns=MANIFEST_COLS)
    return pd.read_csv(mp, comment="#")


def _git_sha() -> str:
    """当前 HEAD 的短 sha；不是 git 仓库时返回空串。"""
    try:
        import subprocess

        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return ""


def sha16(path: str | Path, chunk: int = 1 << 20) -> str:
    """文件 sha256 的前 16 位 —— 检测"同一条命令两次产出不同文件"。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- meta.json
def write_meta(directory: str | Path, name: str, payload: Mapping) -> Path:
    base = Path(directory)
    if not base.is_absolute():
        base = data_root() / base
    p = ensure_dir(base) / name
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def read_meta(directory: str | Path, name: str) -> dict:
    base = Path(directory)
    if not base.is_absolute():
        base = data_root() / base
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 面板
def build_panel(features_long: pd.DataFrame, labels_long: pd.DataFrame,
                *, key_factor: str = "factor", key_label: str = "label") -> pd.DataFrame:
    """features(长) ⨝ labels(长) → 面板（行 = (date, ticker)）。

    约定：缺失一律 NaN，**不填充**；是否剔除由评估代码决定（见 data_layer.md §3.4）。
    """
    f = features_long.pivot_table(index=["date", "ticker"], columns=key_factor,
                                  values="value", aggfunc="first")
    lab = labels_long.pivot_table(index=["date", "ticker"], columns=key_label,
                                  values="value", aggfunc="first")
    panel = f.join(lab, how="outer")
    panel.columns.name = None
    return panel.reset_index().sort_values(["date", "ticker"]).reset_index(drop=True)


def panel_zscore(panel: pd.DataFrame, cols: Iterable[str],
                 by: Iterable[str] = ("date",), clip: float = 3.0,
                 suffix: str = "_z") -> pd.DataFrame:
    """按组（默认 date，可加 pool）计算 z-score 并截尾 ±clip。

    与旧项目一致：``((x - mean) / std(ddof=0)).clip(±clip)``；NaN 保持 NaN。
    """
    out = panel.copy()
    g = out.groupby(list(by), observed=True)
    for c in cols:
        mean = g[c].transform("mean")
        std = g[c].transform(lambda s: s.std(ddof=0))
        z = (out[c] - mean) / std.replace(0.0, np.nan)
        out[c + suffix] = z.clip(-clip, clip)
    return out
