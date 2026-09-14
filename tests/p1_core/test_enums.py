"""枚举类型测试。"""

from __future__ import annotations

import pytest

from p1_core.models.enums import (
    BlockType,
    ChunkQuality,
    DocumentFormat,
    SourceType,
)


class TestSourceType:
    """数据源枚举。"""

    @pytest.mark.parametrize(
        "member, value",
        [
            (SourceType.PDF, "pdf"),
            (SourceType.WORD, "word"),
            (SourceType.HTML, "html"),
            (SourceType.API, "api"),
            (SourceType.DATABASE, "database"),
            (SourceType.TICKET_12345, "ticket_12345"),
            (SourceType.MANUAL, "manual"),
        ],
    )
    def test_value(self, member: SourceType, value: str) -> None:
        assert member.value == value

    def test_str_inherits(self) -> None:
        assert isinstance(SourceType.PDF, str)
        assert SourceType.PDF == "pdf"


class TestDocumentFormat:
    """文档格式枚举。"""

    @pytest.mark.parametrize(
        "member, value",
        [
            (DocumentFormat.PDF, "pdf"),
            (DocumentFormat.DOCX, "docx"),
            (DocumentFormat.HTML, "html"),
            (DocumentFormat.TEXT, "text"),
        ],
    )
    def test_value(self, member: DocumentFormat, value: str) -> None:
        assert member.value == value


class TestBlockType:
    """解析块枚举。"""

    @pytest.mark.parametrize(
        "member, value",
        [
            (BlockType.HEADING, "heading"),
            (BlockType.PARAGRAPH, "paragraph"),
            (BlockType.TABLE, "table"),
            (BlockType.LIST, "list"),
            (BlockType.IMAGE, "image"),
        ],
    )
    def test_value(self, member: BlockType, value: str) -> None:
        assert member.value == value


class TestChunkQuality:
    """切分块质量枚举。"""

    @pytest.mark.parametrize(
        "member, value",
        [
            (ChunkQuality.OK, "ok"),
            (ChunkQuality.TOO_SHORT, "too_short"),
            (ChunkQuality.DUPLICATE, "duplicate"),
            (ChunkQuality.PARSE_FAILED, "parse_failed"),
            (ChunkQuality.LOW_VALUE, "low_value"),
        ],
    )
    def test_value(self, member: ChunkQuality, value: str) -> None:
        assert member.value == value
