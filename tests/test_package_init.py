"""包级测试入口(确保子包均可见)."""

from __future__ import annotations

import p1_core
import p1_core.collectors
import p1_core.collectors.api
import p1_core.collectors.base
import p1_core.collectors.document
import p1_core.collectors.html
import p1_core.collectors.pdf
import p1_core.parsers
import p1_core.parsers.html
import p1_core.parsers.pdf
import p1_core.parsers.splitter
import p1_core.parsers.word


def test_p1_core_imports() -> None:
    """验证 `p1_core` 顶层模块可导入."""
    assert p1_core.__version__ == "0.1.0"


def test_subpackage_imports() -> None:
    """验证 Stage 2/3 子包可导入."""
    assert p1_core.collectors is not None
    assert p1_core.collectors.api is not None
    assert p1_core.collectors.base is not None
    assert p1_core.collectors.document is not None
    assert p1_core.collectors.html is not None
    assert p1_core.collectors.pdf is not None
    assert p1_core.parsers is not None
    assert p1_core.parsers.html is not None
    assert p1_core.parsers.pdf is not None
    assert p1_core.parsers.splitter is not None
    assert p1_core.parsers.word is not None
