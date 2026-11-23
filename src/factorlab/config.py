"""配置与路径解析。所有模块的唯一入口是这里的 ``load_*`` 函数。

加载顺序（优先级从高到低）：
    环境变量  >  .env  >  configs/default.yaml

凭证只从环境变量 / .env 读，**永不**从 configs/*.yaml 读
（见 README §2 铁律与 .env.example）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# 仓库根 = src/factorlab/config.py 往上三层
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- .env
def _load_dotenv() -> None:
    """极简 .env 解析（避免强依赖 python-dotenv）。不覆盖已有环境变量。"""
    path = REPO_ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()


# ---------------------------------------------------------------- yaml
def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 YAML mapping")
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=None)
def load_config(name: str = "default") -> dict[str, Any]:
    """加载 configs/<name>.yaml，并叠加 configs/local.yaml（若存在，已被 gitignore）。"""
    direct = REPO_ROOT / "configs" / f"{name}.yaml"
    nested = REPO_ROOT / "configs" / name / "default.yaml"
    cfg = _read_yaml(direct if direct.exists() else nested)
    local = REPO_ROOT / "configs" / "local.yaml"
    if local.exists():
        cfg = _deep_merge(cfg, _read_yaml(local))
    return cfg


# ---------------------------------------------------------------- registry
REGISTRY_FILES = {
    "factors": "factors.yaml",
    "labels": "labels.yaml",
    "field_pit": "field_pit.yaml",
    "trials": "trials_log.csv",
}


def registry_path(name: str) -> Path:
    if name not in REGISTRY_FILES:
        raise KeyError(f"未知 registry：{name}，可选 {list(REGISTRY_FILES)}")
    return REPO_ROOT / "registry" / REGISTRY_FILES[name]


def load_registry(name: str):
    """返回 dict（yaml 类）或 DataFrame（trials）。"""
    path = registry_path(name)
    if name == "trials":
        import pandas as pd

        if not path.exists():
            return pd.DataFrame()
        # 跳过 # 注释行
        return pd.read_csv(path, comment="#")
    return _read_yaml(path)


def factor_spec(factor_id: str) -> dict[str, Any]:
    """从 factors.yaml 取一条；找不到直接报错（不允许来路不明的列）。"""
    reg = load_registry("factors")
    for item in reg.get("factors", []):
        if item.get("id") == factor_id:
            return item
    raise KeyError(
        f"因子 {factor_id!r} 未在 registry/factors.yaml 登记。"
        "按 docs/02_methods/research_workflow.md 门 2 先登记。"
    )


def active_factor_ids(status: str | None = "active") -> list[str]:
    reg = load_registry("factors")
    items = reg.get("factors", [])
    if status is None:
        return [f["id"] for f in items]
    return [f["id"] for f in items if f.get("status") == status]


# ---------------------------------------------------------------- paths
def data_root() -> Path:
    """数据根目录。可由 .env 的 FACTORLAB_DATA_ROOT 覆盖（大数据放外部盘）。"""
    env = os.environ.get("FACTORLAB_DATA_ROOT", "").strip()
    return Path(env) if env else REPO_ROOT / "data"


def cache_root() -> Path:
    env = os.environ.get("FACTORLAB_CACHE_ROOT", "").strip()
    if env:
        return Path(env)
    return REPO_ROOT / "artifacts" / "cache"


def artifacts_root() -> Path:
    return REPO_ROOT / "artifacts"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------- 常量
def as_of_time() -> str:
    return str(load_config().get("project", {}).get("as_of_time", "14:30"))


def cost_one_way() -> float:
    return float(load_config().get("costs", {}).get("one_way", 0.0010))


def trading_days_per_year() -> int:
    return int(load_config().get("market", {}).get("trading_days_per_year", 252))


def seed() -> int:
    return int(load_config().get("reproducibility", {}).get("seed", 0))
