"""前视体检（Lookahead Audit）—— 门 6 的第一项，也是最便宜的一项。

四道检查（见 docs/02_methods/lookahead_audit.md）：

    A. 字段覆盖    panel 里每一列能否找到定义（不许有来路不明的列）
    B. shift 复算  声明的 needs_shift 字段，panel 里存的到底是哪一版
    C. 截断不变性  只用 <= as_of 的数据重算，结果必须与全量一致  ★ 最有说服力
    D. 口径差异    修正前后的净年化差（判定线 < 0.5pp）

用法::

    python -m factorlab.audit.lookahead --panel data/panels/panel_*.parquet
    python -m factorlab.audit.lookahead --registry-only      # 只查注册表一致性
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from factorlab.config import load_registry, registry_path

# panel 里允许出现的"非因子"列（元信息 + 标签前缀）
META_COLS = {
    "date", "ticker", "order_book_id", "pool", "entry", "tradable",
    "v1430", "day_amt", "score", "rank", "weight",
}
LABEL_PREFIXES = ("ret_",)


@dataclass
class AuditResult:
    name: str
    passed: bool
    detail: str
    severity: str = "error"          # error | warn | info

    def line(self) -> str:
        mark = "ok  " if self.passed else f"{self.severity.upper():4s}"
        return f"   - {mark} {self.name:26s} {self.detail}"


@dataclass
class AuditReport:
    subject: str
    results: list[AuditResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity == "error")

    def add(self, *a, **kw) -> None:
        self.results.append(AuditResult(*a, **kw))

    def text(self) -> str:
        head = f"{'判定':<4} {'PASS' if self.passed else 'FAIL'}   {self.subject}"
        return "\n".join([head, *(r.line() for r in self.results)])

    def to_json(self) -> str:
        return json.dumps({
            "subject": self.subject, "passed": self.passed,
            "results": [{"check": r.name, "passed": r.passed,
                         "detail": r.detail, "severity": r.severity}
                        for r in self.results],
        }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 已知字段集
def known_field_names() -> set[str]:
    """field_pit.yaml 里登记的全部字段名。"""
    pit = load_registry("field_pit")
    fields = pit.get("fields", {})
    names = set(fields) if isinstance(fields, dict) else set()
    if not names:
        names = {item.get("name", "") for item in fields} - {""}
    return names


def known_factor_names() -> set[str]:
    reg = load_registry("factors")
    return {f["id"] for f in reg.get("factors", []) if f.get("id")}


def known_label_names() -> set[str]:
    reg = load_registry("labels")
    return {lab["id"] for lab in reg.get("labels", []) if lab.get("id")}


# ---------------------------------------------------------------- A. 覆盖
def check_field_coverage(panel: pd.DataFrame,
                         extra_ok: Iterable[str] = ()) -> AuditResult:
    """panel 的每一列必须能归入：元信息 / 标签 / 已登记因子 / 已登记字段。

    任何"查不到出处的列"直接判失败 —— 三个月后你不会记得 ``foo_ratio`` 是什么，
    而它正在决定选股。
    """
    ok = (META_COLS | known_field_names() | known_factor_names()
          | known_label_names() | set(extra_ok))
    unknown = sorted(
        c for c in panel.columns
        if c not in ok
        and not str(c).startswith(LABEL_PREFIXES)
        and not str(c).endswith("_z")
        and not str(c).startswith("_")
    )
    return AuditResult(
        "A.field_coverage", not unknown,
        "ok" if not unknown else f"{len(unknown)} 列来路不明：{unknown[:6]}",
    )


# ---------------------------------------------------------------- A2. 声明完备
def check_pit_declarations() -> list[AuditResult]:
    """注册表一致性：每个因子的 pit_fields 都要在 field_pit.yaml 里。

    这是"声明完备"，**不是**"shift 正确" —— 后者只能靠 B/C 检查。
    """
    pit = known_field_names()
    out: list[AuditResult] = []
    missing: dict[str, list[str]] = {}
    needs_shift_undeclared: list[str] = []

    reg = load_registry("factors")
    for f in reg.get("factors", []):
        fid = f.get("id", "?")
        for fld in f.get("pit_fields", []) or []:
            if fld not in pit:
                missing.setdefault(fid, []).append(fld)
        # active 因子必须有退役条件
        if f.get("status") == "active" and not f.get("retire_if"):
            needs_shift_undeclared.append(fid)

    out.append(AuditResult(
        "A2.pit_fields_registered", not missing,
        "ok" if not missing else f"未登记字段：{ {k: v for k, v in list(missing.items())[:5]} }",
    ))
    out.append(AuditResult(
        "A2.active_has_retire_if", not needs_shift_undeclared,
        "ok" if not needs_shift_undeclared else f"缺退役条件：{needs_shift_undeclared}",
    ))

    # rejected 必须有死因
    no_reason = [f.get("id") for f in reg.get("factors", [])
                 if f.get("status") == "rejected" and not f.get("reject_reason")]
    out.append(AuditResult(
        "A2.rejected_has_reason", not no_reason,
        "ok" if not no_reason else f"缺死因：{no_reason}",
    ))
    return out


# ---------------------------------------------------------------- B. shift 版本
def check_shift_version(panel_col: pd.Series, v_with_today: pd.Series,
                        v_lagged: pd.Series, *, atol: float = 1e-10,
                        name: str = "B.shift_version") -> AuditResult:
    """panel 里这一列，匹配的是"含今日"还是"滞后一日"版本？

    ``v_with_today`` / ``v_lagged`` 由调用者用 curated 原始数据重算并传入
    （本模块不猜数据形状）。
    """
    a = pd.Series(panel_col).reindex(v_with_today.index)
    same_today = float((np.isclose(a, v_with_today, atol=atol, equal_nan=True)).mean())
    same_lag = float((np.isclose(a, v_lagged, atol=atol, equal_nan=True)).mean())

    if same_lag >= max(same_today, 0.99):
        return AuditResult(name, True, f"匹配 T-1 口径（{same_lag:.1%}）")
    if same_today >= max(same_lag, 0.99):
        return AuditResult(
            name, False,
            f"⚠️ 匹配「含今日」口径（{same_today:.1%}）—— 与 field_pit.yaml 的 needs_shift 冲突")
    return AuditResult(
        name, False,
        f"两版都不匹配（含今日 {same_today:.1%}, T-1 {same_lag:.1%}）—— 请检查构造逻辑")


# ---------------------------------------------------------------- C. 截断不变性
def check_truncation_invariance(
    dates: Iterable,
    *,
    recompute_full: Callable[[object], object],
    recompute_truncated: Callable[[object], object],
    keys: Callable[[object], set] | None = None,
) -> list[AuditResult]:
    """★ 决定性检验：删掉 as_of 之后的数据，结果必须不变。

    Parameters
    ----------
    dates
        要抽查的日期（建议含：长假后、市场极端日、预热期刚结束、随机若干）。
    recompute_full / recompute_truncated
        两个回调，入参是日期，返回该日的"决策结果"（通常是选出的股票集合）。
    keys
        把返回值转成可比较的集合；默认直接当作集合。

    Returns
    -------
    每个日期一个 AuditResult。

    为什么这条最有说服力：**如果结果依赖"未来才存在的数据"，删掉未来必然变化。**
    旧项目 cls_pool 用它做 PIT 校验，8/8 通过。
    """
    out: list[AuditResult] = []
    conv = keys or (lambda x: set(x) if not isinstance(x, set) else x)
    for d in dates:
        try:
            full = conv(recompute_full(d))
            trunc = conv(recompute_truncated(d))
        except Exception as exc:  # noqa: BLE001
            out.append(AuditResult(f"C.truncation@{d}", False, f"重算失败：{exc!r}"))
            continue
        same = full == trunc
        diff = len(full.symmetric_difference(trunc)) if not same else 0
        out.append(AuditResult(
            f"C.truncation@{d}", same,
            "ok" if same else f"差异 {diff} 个（说明用到了 as_of 之后的数据）"))
    return out


# ---------------------------------------------------------------- D. 口径差异
def check_impact(before: float, after: float, *,
                 threshold_pp: float = 0.5,
                 name: str = "D.impact") -> AuditResult:
    """修正前后净年化的差（小数输入，pp 判定）。

    判定线：跌幅 < 0.5pp 通过；> 1.0pp 说明有真问题。
    """
    delta_pp = (after - before) * 100.0
    if abs(delta_pp) < threshold_pp:
        return AuditResult(name, True, f"影响 {delta_pp:+.2f}pp（< {threshold_pp}pp）")
    sev = "error" if abs(delta_pp) > 1.0 else "warn"
    return AuditResult(
        name, False,
        f"影响 {delta_pp:+.2f}pp（阈值 {threshold_pp}pp）—— "
        f"{'需要单独解释' if sev == 'warn' else '说明有真问题，必须查清'}",
        severity=sev)


# ---------------------------------------------------------------- 汇总
def audit_panel(panel: pd.DataFrame,
                extra_ok: Iterable[str] = ()) -> AuditReport:
    rep = AuditReport(subject="panel 前视体检")
    rep.results.append(check_field_coverage(panel, extra_ok))
    rep.results.extend(check_pit_declarations())
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="前视体检")
    ap.add_argument("--panel", help="panel parquet 路径")
    ap.add_argument("--registry-only", action="store_true", help="只查注册表一致性")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.registry_only or not args.panel:
        rep = AuditReport(subject="注册表一致性（不含 panel）")
        rep.results.extend(check_pit_declarations())
        rep.add("A.field_coverage", True, "skipped（未提供 --panel）", severity="info")
    else:
        panel = pd.read_parquet(args.panel)
        rep = audit_panel(panel)

    print(rep.to_json() if args.json else rep.text())
    print()
    print("说明：A/B/D 可自动化；B 需要传入两版重算结果，C 需要传入两个回调。")
    print("      完整用法见 docs/02_methods/lookahead_audit.md。")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
