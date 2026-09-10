"""模型层共享校验工具。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from p1_core.exceptions import ValidationError


def require_nonempty_str(value: object, *, field: str) -> str:
    """校验 `value` 是非空字符串,否则抛出 `ValidationError`."""
    if not isinstance(value, str):
        msg = f"{field} must be str, got {type(value).__name__}"
        raise ValidationError(msg)
    stripped = value.strip()
    if not stripped:
        msg = f"{field} must be non-empty"
        raise ValidationError(msg)
    return stripped


def require_aware_datetime(value: object, *, field: str) -> datetime:
    """校验 `value` 是带时区的 `datetime`,否则抛出 `ValidationError`."""
    if not isinstance(value, datetime):
        msg = f"{field} must be datetime, got {type(value).__name__}"
        raise ValidationError(msg)
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        msg = f"{field} must be timezone-aware"
        raise ValidationError(msg)
    return value


def require_str_dict(value: object, *, field: str) -> dict[str, str]:
    """校验 `value` 是 `Mapping[str, str]` 并返回其浅拷贝.

    `dataclass(frozen=True, slots=True)` 已阻止字段重赋值;此处额外返回拷贝
    以避免构造期输入与实例字段共享同一引用.返回 `dict` 而非 `MappingProxyType`
    是为了保证 `dataclass` 默认 `__hash__` 可用.
    """
    if not isinstance(value, Mapping):
        msg = f"{field} must be Mapping[str, str], got {type(value).__name__}"
        raise ValidationError(msg)
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            msg = f"{field} entries must be str -> str"
            raise ValidationError(msg)
    return dict(value)


def require_positive_page(page: object, *, field: str) -> int | None:
    """校验 `page` 是正整数或 `None`."""
    if page is None:
        return None
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        msg = f"{field} must be positive int or None"
        raise ValidationError(msg)
    return page


def require_line_range(value: object, *, field: str) -> tuple[int, int] | None:
    """校验 `value` 是 `(start, end)` 形式且满足 1 <= start <= end."""
    if value is None:
        return None
    if not isinstance(value, tuple) or len(value) != 2:
        msg = f"{field} must be (int, int) or None"
        raise ValidationError(msg)
    start, end = value
    if not isinstance(start, int) or isinstance(start, bool):
        msg = f"{field}[0] must be int"
        raise ValidationError(msg)
    if not isinstance(end, int) or isinstance(end, bool):
        msg = f"{field}[1] must be int"
        raise ValidationError(msg)
    if start < 1 or end < start:
        msg = f"{field} must satisfy 1 <= start <= end"
        raise ValidationError(msg)
    return (start, end)


__all__ = [
    "require_aware_datetime",
    "require_line_range",
    "require_nonempty_str",
    "require_positive_page",
    "require_str_dict",
]
