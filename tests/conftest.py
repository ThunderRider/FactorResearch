"""pytest 引导：把 ``src/`` 加进 sys.path，使测试无需安装即可运行。

    pytest -q
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
