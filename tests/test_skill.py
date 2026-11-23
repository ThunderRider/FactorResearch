"""技能契约测试：`factor-research-workflow` 这个 skill 必须始终与本仓库一致。

skill 装在用户级目录（``$DSH_HOME/skills/factor-research-workflow``），仓库里没有它时自动跳过；
装了就必须过下面这些检查——否则"技能说的"会和"仓库做的"漂移。

    pytest tests/test_skill.py -q
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LEGACY_KEYS = {"disableModelInvocation", "modelInvocable", "userInvocable"}
MAX_DESC = 500          # dsh-tool-skill 的 catalogDescriptionMaxLength 默认值
REQUIRED_TOKENS = ("0.200%", "0.5pp", "0.95", "60%", "0.10")
DATA_SKIP = ("data/raw/", "data/curated/", "data/features/", "data/labels/", "data/panels/")
DATA_COMMITTED = {"data/README.md", "data/MANIFEST.csv"}


def _skill_dir() -> Path:
    env = os.environ.get("FACTOR_RESEARCH_SKILL_DIR")
    if env:
        return Path(env)
    home = os.environ.get("DSH_HOME") or str(Path.home() / ".dsh")
    return Path(home) / "skills" / "factor-research-workflow"


SKILL_DIR = _skill_dir()
pytestmark = pytest.mark.skipif(
    not (SKILL_DIR / "SKILL.md").exists(),
    reason=f"未安装技能：{SKILL_DIR}/SKILL.md",
)


def _split(text: str) -> tuple[dict, str]:
    lines = text.split("\n")
    assert lines and lines[0].strip() == "---", "首行必须是 '---'"
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    return yaml.safe_load("\n".join(lines[1:end])), "\n".join(lines[end + 1:])


@pytest.fixture(scope="module")
def skill():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    fm, body = _split(text)
    return fm, body, text


# ---------------------------------------------------------------- 前端元数据
def test_frontmatter_is_valid(skill):
    fm, _, _ = skill
    assert isinstance(fm, dict)
    name, desc = fm.get("name"), fm.get("description")
    assert isinstance(name, str) and NAME_RE.match(name), f"name 不合法：{name!r}"
    assert name == SKILL_DIR.name, "name 必须与目录名一致"
    assert isinstance(desc, str) and desc.strip(), "description 不能为空"
    assert len(desc) <= MAX_DESC, f"description {len(desc)} 字符，超过会话目录上限 {MAX_DESC}"


def test_frontmatter_has_no_legacy_keys(skill):
    fm, _, _ = skill
    bad = LEGACY_KEYS & set(fm)
    assert not bad, f"旧式驼峰键会被拒绝：{bad}"


# ---------------------------------------------------------------- 内容必须对得上仓库
def test_referenced_repo_paths_exist(skill):
    _, body, _ = skill
    found = re.findall(r"\b((?:docs|registry|configs|src|research|tests)/[A-Za-z0-9_./*-]+)",
                       body)
    missing = []
    for raw in sorted(set(found)):
        p = raw.rstrip(".,;)")
        if any(ch in p for ch in "*<>"):
            continue
        if p.startswith(DATA_SKIP) and p not in DATA_COMMITTED:
            continue
        if not (REPO / p).exists():
            missing.append(p)
    assert not missing, f"技能引用了不存在的路径：{missing}"


def test_referenced_modules_exist(skill):
    _, body, _ = skill
    mods = set(re.findall(r"factorlab\.((?:[a-z_]+\.)*[a-z_]+)", body))
    missing = []
    for mod in sorted(mods):
        target = REPO / "src" / "factorlab" / Path(*mod.split("."))
        if not (target.with_suffix(".py").exists() or target.is_dir()):
            missing.append(f"factorlab.{mod}")
    assert not missing, f"技能引用了不存在的模块：{missing}"


def test_thresholds_are_all_present(skill):
    _, body, _ = skill
    missing = [t for t in REQUIRED_TOKENS if t not in body]
    assert not missing, f"技能漏掉了判定线：{missing}"


def test_test_baseline_matches_reality(skill):
    """技能里写的 "N passed" 必须等于真实用例数（防止漂移）。"""
    _, body, _ = skill
    m = re.search(r"(\d+) passed", body)
    assert m, "技能应写明测试基线（例如 55 passed）"
    claimed = int(m.group(1))
    count = sum(
        len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M))
        for p in (REPO / "tests").glob("test_*.py")
    )
    assert claimed == count, f"技能写 {claimed} passed，实际有 {count} 个用例"


def test_thresholds_match_config(skill):
    """判定线必须与 configs/ 一致，不能各写一套。"""
    from factorlab.config import load_config

    evals = load_config("evals")
    body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert evals["independence"]["keep_ratio_pass"] == 0.60
    assert evals["importance"]["delta_sharpe_pass"] == 0.10
    assert evals["portfolio"]["breakeven_daily_per_unit_exposure"] == 0.002
    assert "60%" in body and "0.10" in body and "0.200%" in body


# ---------------------------------------------------------------- 资源
def test_referenced_resources_exist(skill):
    _, body, _ = skill
    for rel in re.findall(r"\]\(([^)#:]+?)\)", body):
        if rel.startswith("http"):
            continue
        assert (SKILL_DIR / rel).exists(), f"技能内相对链接失效：{rel}"


def test_checklists_covers_every_gate(skill):
    """检查单必须覆盖 7 道门的每一道（否则等于允许跳门）。"""
    path = SKILL_DIR / "references" / "checklists.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    for gate in ("门 1", "门 2", "门 3", "门 4", "门 5", "门 6", "门 7"):
        assert gate in text, f"checklists.md 缺少 {gate}"
    for word in ("开工清单", "收尾自检", "评审模式"):
        assert word in text, f"checklists.md 缺少 {word}"


def test_three_iron_laws_are_all_enforced(skill):
    """三条铁律必须各自带"验收/禁止"的可判定内容。"""
    _, body, _ = skill
    for law in ("铁律 1", "铁律 2", "铁律 3"):
        assert law in body, f"缺少 {law}"
    assert "lookahead" in body, "铁律 1 必须指向前视体检命令"
    assert "log_trial" in body, "铁律 2 必须给出记账 API"
    assert "先判死" in body or "判死" in body, "铁律 3 必须写明先判死再优化"
