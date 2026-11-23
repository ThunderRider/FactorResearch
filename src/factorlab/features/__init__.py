"""因子构造子包。

约定：每个函数"输入矩阵 → 输出矩阵"，不做标准化、不做 PIT 修正
（PIT 由输入列的选择保证，见 registry/field_pit.yaml）。
"""

from __future__ import annotations

__all__ = ["price_volume", "bar_stats", "snapshot"]
