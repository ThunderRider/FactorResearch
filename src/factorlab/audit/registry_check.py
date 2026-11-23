"""注册表一致性检查 —— 建议设为 pre-commit 钩子。

一致性靠检查，不靠自觉。

用法::

    python -m factorlab.audit.registry_check
    python -m factorlab.audit.registry_check --strict    # 有 warn 也返回非 0
"""

from __future__ import annotations

import argparse
import sys

from factorlab.audit.lookahead import check_pit_declarations
from factorlab.audit.trials import load_trials, report as trials_report, total_n
from factorlab.config import REPO_ROOT, load_registry

VALID_STATUS = {
    "draft", "candidate", "active", "watch", "retired",
    "rejected", "input", "control",
}
VALID_DIRECTION = {"positive", "negative", "none", "unknown"}


def run(strict: bool = False) -> int:
    problems: list[str] = []
    warnings: list[str] = []

    reg = load_registry("factors")
    factors = reg.get("factors", [])
    ids = [f.get("id") for f in factors]

    # 1. 唯一性
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        problems.append(f"因子 id 重复：{sorted(dupes)}")

    # 2. 必填字段 + 枚举
    for f in factors:
        fid = f.get("id", "<no-id>")
        for key in ("id", "label", "family", "status", "direction"):
            if not f.get(key):
                problems.append(f"{fid}: 缺少必填字段 {key!r}")
        if f.get("status") not in VALID_STATUS:
            problems.append(f"{fid}: status={f.get('status')!r} 不在 {sorted(VALID_STATUS)}")
        if f.get("direction") not in VALID_DIRECTION:
            problems.append(f"{fid}: direction={f.get('direction')!r} 不在 {sorted(VALID_DIRECTION)}")
        if f.get("status") == "active":
            if not f.get("evidence"):
                problems.append(f"{fid}: status=active 但 evidence 为空")
            if not f.get("retire_if"):
                problems.append(f"{fid}: status=active 但缺 retire_if（退役条件）")
        if f.get("status") == "rejected" and not f.get("reject_reason"):
            problems.append(f"{fid}: status=rejected 但缺 reject_reason")

    # 3. PIT 声明
    for r in check_pit_declarations():
        if r.passed:
            continue
        bucket = problems if r.severity == "error" else warnings
        bucket.append(f"{r.name}: {r.detail}")

    # 4. 标签引用
    labels = {lab.get("id") for lab in load_registry("labels").get("labels", [])}
    for f in factors:
        for lab in f.get("labels", []) or []:
            if lab not in labels:
                problems.append(f"{f.get('id')}: 引用了未登记的标签 {lab!r}")

    # 5. 试验记账
    tr = load_trials()
    if tr.empty:
        warnings.append("trials_log.csv 为空 —— 还没记过账")
    else:
        missing_sha = tr[tr["git_sha"].fillna("").astype(str).str.strip() == ""]
        if len(missing_sha):
            warnings.append(f"{len(missing_sha)} 行试验缺 git_sha（不可复现）")

    # 6. 结论文档是否存在
    for doc in ("docs/03_knowledge/factor_zoo.md",
                "docs/03_knowledge/falsified.md",
                "docs/03_knowledge/lessons_learned.md"):
        if not (REPO_ROOT / doc).exists():
            warnings.append(f"缺少知识文档 {doc}")

    # ---- 输出
    print(f"因子 {len(factors)} 条，状态分布：")
    dist: dict[str, int] = {}
    for f in factors:
        dist[f.get("status", "?")] = dist.get(f.get("status", "?"), 0) + 1
    for k in sorted(dist):
        print(f"   {k:<10} {dist[k]}")
    print()
    print(trials_report(tr))
    print()

    if warnings:
        print(f"WARN ({len(warnings)})")
        for w in warnings:
            print(f"   - {w}")
    if problems:
        print(f"ERROR ({len(problems)})")
        for p in problems:
            print(f"   ! {p}")
        return 1

    print("一致性检查通过。")
    return 1 if (strict and warnings) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="registry 一致性检查")
    ap.add_argument("--strict", action="store_true", help="有 warn 也返回非 0")
    args = ap.parse_args(argv)
    return run(strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
