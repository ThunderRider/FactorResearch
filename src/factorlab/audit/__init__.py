"""审计子包：前视、DSR、PBO、置换重要性、试验记账、注册表检查。

这一层是旧项目**完全缺失**的部分（见 docs/02_methods/overfitting_controls.md §0）。
"""

from __future__ import annotations

__all__ = ["dsr", "pbo", "permutation", "trials", "lookahead", "registry_check"]
