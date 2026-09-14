"""切分阶段产物：`KnowledgeChunk`。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models._validators import (
    require_line_range,
    require_nonempty_str,
    require_positive_page,
)
from p1_core.models.enums import ChunkQuality
from p1_core.models.heading import HeadingPath


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """切分阶段产物，最小语义单元。

    Attributes:
        chunk_id: 块标识。
        raw_doc_id: 关联的原始文档 ID。
        parsed_doc_id: 关联的解析文档标识（解析阶段产出 ID，未来扩展）。
        heading_path: 块所属标题层级路径（必填）。
        text: 块文本内容。
        page: 所在页码。
        line_range: 起止行号（含）。
        parent_chunk_id: 父块 ID（章节关联文档），用于召回后还原上下文。
        quality_flag: 块质量标记（OK/TOO_SHORT/...）。
    """

    chunk_id: str
    raw_doc_id: str
    parsed_doc_id: str
    heading_path: HeadingPath
    text: str
    page: int | None
    line_range: tuple[int, int] | None
    parent_chunk_id: str | None
    quality_flag: ChunkQuality

    def __post_init__(self) -> None:
        require_nonempty_str(self.chunk_id, field="chunk_id")
        require_nonempty_str(self.raw_doc_id, field="raw_doc_id")
        require_nonempty_str(self.parsed_doc_id, field="parsed_doc_id")
        if not isinstance(self.text, str):
            msg = "text must be str"
            raise ValidationError(msg)
        require_positive_page(self.page, field="page")
        require_line_range(self.line_range, field="line_range")

    def to_dict(self) -> dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return {
            "chunk_id": self.chunk_id,
            "raw_doc_id": self.raw_doc_id,
            "parsed_doc_id": self.parsed_doc_id,
            "heading_path": self.heading_path.to_dict(),
            "text": self.text,
            "page": self.page,
            "line_range": list(self.line_range) if self.line_range else None,
            "parent_chunk_id": self.parent_chunk_id,
            "quality_flag": self.quality_flag.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> KnowledgeChunk:
        """从字典反序列化。"""
        try:
            return cls(
                chunk_id=_expect_str(data, "chunk_id"),
                raw_doc_id=_expect_str(data, "raw_doc_id"),
                parsed_doc_id=_expect_str(data, "parsed_doc_id"),
                heading_path=_parse_heading_path(data["heading_path"]),
                text=_expect_str(data, "text"),
                page=_parse_optional_int(data.get("page"), field="page"),
                line_range=_parse_optional_line_range(data.get("line_range"), field="line_range"),
                parent_chunk_id=_parse_optional_str(
                    data.get("parent_chunk_id"), field="parent_chunk_id"
                ),
                quality_flag=ChunkQuality(_expect_str(data, "quality_flag")),
            )
        except KeyError as exc:
            msg = f"KnowledgeChunk missing key: {exc.args[0]}"
            raise SerializationError(msg) from exc
        except (TypeError, ValueError) as exc:
            msg = f"KnowledgeChunk deserialization failed: {exc}"
            raise SerializationError(msg) from exc


def _expect_str(data: Mapping[str, object], key: str) -> str:
    """从映射中取出指定键并要求为 `str`；缺失或类型不符抛 `SerializationError`。"""
    value = data[key]
    if not isinstance(value, str):
        msg = f"{key} must be str, got {type(value).__name__}"
        raise SerializationError(msg)
    return value


def _parse_heading_path(value: object) -> HeadingPath:
    """校验并解析 HeadingPath 字段。"""
    if not isinstance(value, Mapping):
        msg = "KnowledgeChunk.heading_path must be Mapping"
        raise SerializationError(msg)
    return HeadingPath.from_dict(value)


def _parse_optional_int(value: object, *, field: str) -> int | None:
    """将值解析为 `int` 或 `None`；不允许 `bool`。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field} must be int or None"
        raise SerializationError(msg)
    return value


def _parse_optional_line_range(value: object, *, field: str) -> tuple[int, int] | None:
    """将值解析为 `(int, int)` 元组或 `None`。"""
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        msg = f"{field} must be (int, int) or None"
        raise SerializationError(msg)
    start_obj, end_obj = value
    if (
        isinstance(start_obj, bool)
        or isinstance(end_obj, bool)
        or not isinstance(start_obj, int)
        or not isinstance(end_obj, int)
    ):
        msg = f"{field} entries must be int"
        raise SerializationError(msg)
    return (start_obj, end_obj)


def _parse_optional_str(value: object, *, field: str) -> str | None:
    """将值解析为 `str` 或 `None`。"""
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{field} must be str or None"
        raise SerializationError(msg)
    return value


__all__ = ["KnowledgeChunk"]
