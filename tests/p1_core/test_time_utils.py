"""`utcnow` 时间工具测试。"""

from __future__ import annotations

from datetime import UTC

from p1_core.models.time_utils import utcnow


def test_utcnow_returns_aware_datetime() -> None:
    dt = utcnow()
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt) is not None


def test_utcnow_is_close_to_utc() -> None:
    dt = utcnow()
    offset = dt.utcoffset()
    assert offset is not None
    assert offset == UTC.utcoffset(dt)
