"""数据源与文档格式枚举。

集中放置所有枚举类型，方便在序列化时统一处理字符串 ↔ 枚举映射。
"""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    """数据源类型。"""

    PDF = "pdf"
    WORD = "word"
    HTML = "html"
    API = "api"
    DATABASE = "database"
    TICKET_12345 = "ticket_12345"
    MANUAL = "manual"


class DocumentFormat(StrEnum):
    """解析阶段识别的文档格式。"""

    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    TEXT = "text"


class BlockType(StrEnum):
    """解析中间块的语义类型。"""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"


class ChunkQuality(StrEnum):
    """切分块的质量标记。"""

    OK = "ok"
    TOO_SHORT = "too_short"
    DUPLICATE = "duplicate"
    PARSE_FAILED = "parse_failed"
    LOW_VALUE = "low_value"


__all__ = ["BlockType", "ChunkQuality", "DocumentFormat", "SourceType"]
