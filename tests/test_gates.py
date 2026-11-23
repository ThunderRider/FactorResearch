"""门 4（正交化）与门 6（禁运）的回归测试。

这两道门在旧项目里**完全缺失**（见 docs/02_methods/overfitting_controls.md §0），
所以它们最容易在没有测试的情况下被改错。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factorlab.audit import purge
from factorlab.eval import orth


@pytest.fixture
def proxy_panel() -> pd.DataFrame:
    """factor 只是 control 的包装：正交后 IC 应大幅缩水。"""
    rng = np.random.default_rng(7)
    rows = []
    dates = pd.bdate_range("2025-01-01", periods=60)
    for d in dates:
        control = rng.normal(size=50)
        signal = rng.normal(size=50)
        rows.append(pd.DataFrame({
            "date": d,
            "ticker": [f"{i:06d}.XSHE" for i in range(50)],
            "control": control,
            # 因子 = control + 少量噪声 → 它的预测力几乎全来自 control
            "factor": 3.0 * control + 0.1 * signal,
            "label": 0.002 * control + 0.0005 * signal + rng.normal(0, 0.004, 50),
        }))
    return pd.concat(rows, ignore_index=True)


@pytest.fixture
def genuine_panel() -> pd.DataFrame:
    """factor 含有 control 之外的独立信号：正交后 IC 应保留大部分。"""
    rng = np.random.default_rng(11)
    rows = []
    dates = pd.bdate_range("2025-01-01", periods=60)
    for d in dates:
        control = rng.normal(size=50)
        signal = rng.normal(size=50)
        rows.append(pd.DataFrame({
            "date": d,
            "ticker": [f"{i:06d}.XSHE" for i in range(50)],
            "control": control,
            "factor": 0.2 * control + signal,
            "label": 0.002 * signal + rng.normal(0, 0.004, 50),
        }))
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------- 门 4
def test_orthogonalize_removes_control_exposure(proxy_panel):
    """残差与 control 的相关必须接近 0（截面回归的定义）。"""
    resid = orth.orthogonalize(proxy_panel, "factor", ["control"])
    work = proxy_panel.assign(resid=resid).dropna(subset=["resid"])

    def _corr(g: pd.DataFrame) -> float:
        return float(g["resid"].corr(g["control"]))

    by_date = work.groupby("date").apply(_corr, include_groups=False)
    assert by_date.abs().max() < 1e-6


def test_proxy_factor_loses_its_ic(proxy_panel):
    """暴露型因子正交后 IC 保留率应远低于 60%（判定线）。"""
    r = orth.ic_retention(proxy_panel, "factor", "label", ["control"])
    assert r["raw_ic"] > 0
    assert r["retention"] < 0.6, f"代理因子的保留率不该是 {r['retention']:.2f}"


def test_genuine_factor_keeps_its_ic(genuine_panel):
    """独立因子正交后 IC 保留率应 > 60%。"""
    r = orth.ic_retention(genuine_panel, "factor", "label", ["control"])
    assert r["retention"] > 0.6, f"独立因子的保留率只有 {r['retention']:.2f}"
    assert r["sign_flip"] is False


def test_sign_flip_is_flagged():
    """正交后符号翻转 —— 旧项目 amihud 的形态，必须被识别出来。"""
    rng = np.random.default_rng(3)
    rows = []
    for d in pd.bdate_range("2025-01-01", periods=40):
        control = rng.normal(size=40)
        signal = rng.normal(size=40)
        rows.append(pd.DataFrame({
            "date": d,
            "ticker": [f"{i:06d}.XSHE" for i in range(40)],
            "control": control,
            "factor": control + 0.8 * signal,     # 原始 IC 由 control 主导
            "label": control - 0.5 * signal,      # 剔除 control 后残差方向反转
        }))
    panel = pd.concat(rows, ignore_index=True)
    r = orth.ic_retention(panel, "factor", "label", ["control"])
    assert r["sign_flip"] is True
    assert r["retention"] < 0


def test_orthogonalize_rejects_unknown_column(proxy_panel):
    with pytest.raises(KeyError):
        orth.orthogonalize(proxy_panel, "factor", ["not_a_column"])


# ---------------------------------------------------------------- 门 6
def test_split_with_embargo_counts():
    idx = pd.bdate_range("2025-01-01", periods=100)
    is_idx, oos_idx = purge.split_with_embargo(idx, "2025-03-01", embargo_days=10)
    assert len(is_idx) + len(oos_idx) == 100 - 20
    assert is_idx.max() < pd.Timestamp("2025-03-01")
    assert oos_idx.min() >= pd.Timestamp("2025-03-01")


def test_embargo_reduces_oos_sample():
    idx = pd.bdate_range("2025-01-01", periods=200)
    _, a = purge.split_with_embargo(idx, "2025-06-01", embargo_days=0)
    _, b = purge.split_with_embargo(idx, "2025-06-01", embargo_days=30)
    assert len(b) == len(a) - 30


def test_oos_metrics_reports_three_required_fields():
    """报告三要素：切分日 / 禁运长度 / OOS 有效天数。"""
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2025-01-01", periods=300)
    daily = pd.Series(rng.normal(0.001, 0.01, 300), index=idx)
    r = purge.oos_metrics(daily, split="2025-06-01", embargo_days=20)
    assert {"split", "embargo_days", "oos_n", "oos_sharpe"} <= set(r)
    assert r["embargo_days"] == 20
    assert r["oos_n"] > 0


def test_embargo_sensitivity_monotone_decay_shape():
    rng = np.random.default_rng(9)
    idx = pd.bdate_range("2025-01-01", periods=400)
    daily = pd.Series(rng.normal(0.001, 0.01, 400), index=idx)
    df = purge.embargo_sensitivity(daily, split="2025-06-01",
                                   embargo_grid=(0, 20, 60, 120))
    assert list(df["embargo_days"]) == [0, 20, 60, 120]
    assert "decay_vs_no_embargo" in df.columns
    assert df.loc[df["embargo_days"] == 0, "decay_vs_no_embargo"].iloc[0] == pytest.approx(0.0)
