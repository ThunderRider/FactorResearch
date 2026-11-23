"""factorlab · 因子研究的最小可复用库。

设计原则（见 docs/01_architecture/repo_layout.md）：

1. **只放"被复用两次以上"的逻辑**。一次性的研究代码留在 ``research/<dir>/``。
2. **不依赖 rqdatac**。取数在 ``factorlab.data``（可选依赖），
   其余模块只依赖 numpy / pandas，因此可以脱机跑完全部审计。
3. **形状约定**：宽表 ``date × ticker``（curated），长表 ``date,ticker,key,value``
   （features/labels），面板 ``(date,ticker) × 列``（panels）。
   见 ADR 0002。
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
