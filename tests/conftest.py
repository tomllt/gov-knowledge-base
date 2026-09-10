"""Pytest 配置：确保 src/ 在 sys.path 首位，避免与 tests/ 同名子目录冲突。"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
