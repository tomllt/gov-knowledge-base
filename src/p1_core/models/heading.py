"""标题层级路径。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models._validators import require_nonempty_str


@dataclass(frozen=True, slots=True)
class HeadingPath:
    """标题层级路径。

    表达「第 X 章 / X.X 节 / 段落」之类的语义层级。`parts` 由浅到深排列；
    索引 0 对应顶层标题（如「第 1 章」）。仅含根标题时长度为 1。

    Attributes:
        parts: 各级标题文本组成的不可变元组。
    """

    parts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.parts:
            msg = "HeadingPath.parts must not be empty"
            raise ValidationError(msg)
        for i, p in enumerate(self.parts):
            if not isinstance(p, str) or not p.strip():
                msg = f"HeadingPath.parts[{i}] must be non-empty str"
                raise ValidationError(msg)

    @classmethod
    def root(cls, title: str) -> HeadingPath:
        """以单一顶层标题构造路径。"""
        return cls((require_nonempty_str(title, field="title"),))

    def child(self, title: str) -> HeadingPath:
        """在当前路径末尾追加一级标题，返回新实例。"""
        cleaned = require_nonempty_str(title, field="title")
        return HeadingPath((*self.parts, cleaned))

    def depth(self) -> int:
        """路径深度（即层级数）。"""
        return len(self.parts)

    def as_path_string(self, sep: str = " / ") -> str:
        """以指定分隔符拼接成可读路径字符串。"""
        return sep.join(self.parts)

    def to_dict(self) -> dict[str, list[str]]:
        """序列化为可 JSON 化的字典。"""
        return {"parts": list(self.parts)}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> HeadingPath:
        """从字典反序列化；类型不符时抛出 `SerializationError`。"""
        raw_parts = data.get("parts")
        if not isinstance(raw_parts, list):
            msg = "HeadingPath.parts must be list[str]"
            raise SerializationError(msg)
        parts: list[str] = []
        for part in raw_parts:
            if not isinstance(part, str):
                msg = "HeadingPath.parts must be list[str]"
                raise SerializationError(msg)
            parts.append(part)
        return cls(tuple(parts))


__all__ = ["HeadingPath"]
