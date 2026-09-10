"""时间工具。"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """返回带时区的当前 UTC 时间，避免使用 naive datetime。"""
    return datetime.now(tz=UTC)


__all__ = ["utcnow"]
