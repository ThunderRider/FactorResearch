"""因子评估：IC / 分层 / 稳定性。

所有函数只依赖 numpy / pandas。判定线与必报项见 docs/02_methods/factor_eval.md。
"""

from __future__ import annotations

__all__ = ["ic", "decile", "stability"]
