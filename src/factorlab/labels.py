"""标签（目标收益）构造。

口径是 ``registry/labels.yaml`` 的实现。两条硬规则：

1. 收益存**小数**（0.0123 = +1.23%）
2. 标签可以用"未来"数据（它就是未来）；但**因子绝不能**

三段分解必须满足（tests/test_smoke.py 有断言）::

    ret_1445_next_1115 = (1+ret_tail)(1+ret_overnight)(1+ret_morning) - 1
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- 工具
def _pair_mean(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """两价取均值；只有一个可用时用那个，都缺则 NaN。"""
    return (a.fillna(b) + b.fillna(a)) / 2.0


def _prev_day(df: pd.DataFrame) -> pd.DataFrame:
    """按列取"上一行"（日历位移）。停牌日必须保留在索引里才能保证语义一致。"""
    return df.shift(1)


def _next_day(df: pd.DataFrame) -> pd.DataFrame:
    return df.shift(-1)


def _named(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """给 DataFrame 打一个便于识别的名字（DataFrame 没有 .name，用 attrs）。"""
    out = df.copy()
    out.attrs["label"] = name
    return out


# ---------------------------------------------------------------- 尾盘口径
def ret_1445_next_1115(snap_fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """T 日 14:45 → T+1 日 11:15（旧项目主标签）。

    ``entry = (c1430 + c1500) / 2``、``exit = (next c1100 + next c1130) / 2``。
    """
    need = ("c1430", "c1500", "c1100", "c1130")
    _require(snap_fields, need)
    entry = _pair_mean(snap_fields["c1430"], snap_fields["c1500"])
    exit_ = _pair_mean(_next_day(snap_fields["c1100"]), _next_day(snap_fields["c1130"]))
    return _named(exit_ / entry - 1.0, "ret_1445_next_1115")


def ret_1445_next_1330(snap_fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """T 日 14:45 → T+1 日 13:30。⚠️ 增量 t≈1.28，5bp 滑点即归零（待验证）。"""
    need = ("c1430", "c1500", "c1330")
    _require(snap_fields, need)
    entry = _pair_mean(snap_fields["c1430"], snap_fields["c1500"])
    return _named(_next_day(snap_fields["c1330"]) / entry - 1.0, "ret_1445_next_1330")


def ret_1445_next_0930(snap_fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """T 日 14:45 → T+1 日 9:30 开盘（对照用；旧项目实测 −14.39%）。"""
    need = ("c1430", "c1500", "o1000")
    _require(snap_fields, need)
    entry = _pair_mean(snap_fields["c1430"], snap_fields["c1500"])
    return _named(_next_day(snap_fields["o1000"]) / entry - 1.0, "ret_1445_next_0930")


# ---------------------------------------------------------------- 三段分解
def decompose(snap_fields: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """返回 ``ret_tail`` / ``ret_overnight`` / ``ret_morning`` 三段。

    乘积严格等于 ``ret_1445_next_1115``。

    **为什么必须拆**：因子对"隔夜"和"早盘"的预测力完全不同。
    旧项目正是靠这个发现"V3 比 V1 好"的原因是"隔夜不再亏"
    （V1 隔夜 −13.9bp，V3 +6.7bp），而不是"选得更猛"。
    """
    need = ("c1430", "c1500", "c1100", "c1130", "o1000")
    _require(snap_fields, need)

    entry = _pair_mean(snap_fields["c1430"], snap_fields["c1500"])
    open_next = _next_day(snap_fields["o1000"])
    exit_ = _pair_mean(_next_day(snap_fields["c1100"]), _next_day(snap_fields["c1130"]))

    return {
        "ret_tail": _named(snap_fields["c1500"] / entry - 1.0, "ret_tail"),
        "ret_overnight": _named(open_next / snap_fields["c1500"] - 1.0, "ret_overnight"),
        "ret_morning": _named(exit_ / open_next - 1.0, "ret_morning"),
    }


# ---------------------------------------------------------------- 日频
def ret_nd(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """日频 N 日收益（收盘到收盘），``close`` 必须是日收盘宽表。"""
    return _named(close.shift(-n) / close - 1.0, f"ret_{n}d")


def forward_return(price: pd.DataFrame, n: int = 1) -> pd.DataFrame:
    """通用的"未来 n 期收益"：``p.shift(-n) / p - 1``。"""
    return (price.shift(-n) / price - 1.0)


# ---------------------------------------------------------------- 汇总
def build_all(snap_fields: dict[str, pd.DataFrame],
              include_decompose: bool = True) -> dict[str, pd.DataFrame]:
    """一次算出全部登记过的标签（与 registry/labels.yaml 对应）。"""
    out = {
        "ret_1445_next_1115": ret_1445_next_1115(snap_fields),
        "ret_1445_next_1330": ret_1445_next_1330(snap_fields),
        "ret_1445_next_0930": ret_1445_next_0930(snap_fields),
    }
    if include_decompose:
        out.update(decompose(snap_fields))
    return out


# ---------------------------------------------------------------- 校验
def _require(fields: dict[str, pd.DataFrame], need: tuple[str, ...]) -> None:
    missing = [k for k in need if k not in fields]
    if missing:
        raise KeyError(f"标签构造缺少字段 {missing}（需要 {list(need)}）")


def check_decomposition(snap_fields: dict[str, pd.DataFrame], atol: float = 1e-9) -> bool:
    """验证三段分解的乘积恒等于主标签。tests 里用。"""
    total = ret_1445_next_1115(snap_fields)
    parts = decompose(snap_fields)
    rebuilt = ((1 + parts["ret_tail"]) * (1 + parts["ret_overnight"])
               * (1 + parts["ret_morning"]) - 1.0)
    diff = (rebuilt - total).abs()
    finite = diff.to_numpy()[np.isfinite(diff.to_numpy())]
    return bool(finite.size == 0 or finite.max() <= atol)
