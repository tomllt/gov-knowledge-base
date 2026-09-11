"""`ParsedDocument` 与 `ParsedBlock` 模型测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models.enums import BlockType, DocumentFormat
from p1_core.models.heading import HeadingPath
from p1_core.models.parsed_document import ParsedBlock, ParsedDocument


def _block(**overrides: object) -> ParsedBlock:
    """构造默认 `ParsedBlock`，可按需覆盖字段。"""
    defaults: dict[str, object] = {
        "block_id": "blk-001",
        "block_type": BlockType.PARAGRAPH,
        "text": "本指南说明……",
        "page": 1,
        "line_range": (1, 5),
        "heading_path": None,
    }
    defaults.update(overrides)
    return ParsedBlock(**defaults)


def _parsed_doc(**overrides: object) -> ParsedDocument:
    """构造默认 `ParsedDocument`，可按需覆盖字段。"""
    defaults: dict[str, object] = {
        "raw_doc_id": "01HV3A1B2C3D4E5F6G7H8J9K0L",
        "parsed_at": datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC),
        "format": DocumentFormat.PDF,
        "blocks": (_block(),),
    }
    defaults.update(overrides)
    return ParsedDocument(**defaults)


class TestParsedBlockValidation:
    """`ParsedBlock` 字段校验。"""

    def test_blank_block_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            _block(block_id="")

    def test_non_string_text_raises(self) -> None:
        with pytest.raises(ValidationError):
            _block(text=123)  # type: ignore[arg-type]

    def test_zero_page_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive int"):
            _block(page=0)

    def test_negative_page_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive int"):
            _block(page=-1)

    def test_none_page_allowed(self) -> None:
        block = _block(page=None)
        assert block.page is None

    def test_inverted_line_range_raises(self) -> None:
        with pytest.raises(ValidationError, match="1 <= start <= end"):
            _block(line_range=(5, 3))

    def test_zero_line_range_start_raises(self) -> None:
        with pytest.raises(ValidationError, match="1 <= start <= end"):
            _block(line_range=(0, 5))

    def test_none_line_range_allowed(self) -> None:
        block = _block(line_range=None)
        assert block.line_range is None


class TestParsedBlockSerialization:
    """`ParsedBlock` 序列化往返。"""

    def test_roundtrip_with_heading(self) -> None:
        path = HeadingPath.root("第 1 章").child("1.1")
        block = _block(heading_path=path)
        data = block.to_dict() if hasattr(block, "to_dict") else None
        # ParsedBlock 不直接支持 to_dict（仅在 ParsedDocument 中体现），所以
        # 验证它至少可以放到 ParsedDocument 序列化中。
        pd = _parsed_doc(blocks=(block,))
        restored = ParsedDocument.from_dict(pd.to_dict())
        assert restored.blocks[0].heading_path == path
        assert data is None  # 占位断言，防止 IDE 误删。


class TestParsedDocumentEquality:
    """字段相等即对象相等。"""

    def test_equal_when_all_fields_match(self) -> None:
        a = _parsed_doc()
        b = _parsed_doc()
        assert a == b
        assert hash(a) == hash(b)


class TestParsedDocumentFullText:
    """完整文本拼接。"""

    def test_full_text_concatenates_blocks(self) -> None:
        b1 = _block(block_id="b1", text="第一章。")
        b2 = _block(block_id="b2", text="第二章。")
        pd = _parsed_doc(blocks=(b1, b2))
        assert pd.full_text() == "第一章。\n\n第二章。"

    def test_full_text_custom_separator(self) -> None:
        pd = _parsed_doc(
            blocks=(_block(block_id="b1", text="A"), _block(block_id="b2", text="B")),
        )
        assert pd.full_text(sep="\n") == "A\nB"


class TestParsedDocumentValidation:
    """空值校验。"""

    def test_blank_raw_doc_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            _parsed_doc(raw_doc_id="")

    def test_naive_datetime_raises(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            _parsed_doc(parsed_at=datetime(2026, 1, 1))

    def test_blocks_must_be_tuple(self) -> None:
        with pytest.raises(ValidationError, match="blocks must be tuple"):
            _parsed_doc(blocks=[_block()])  # type: ignore[arg-type]

    def test_blocks_must_contain_parsed_blocks(self) -> None:
        with pytest.raises(ValidationError, match="blocks\\[0\\] must be ParsedBlock"):
            _parsed_doc(blocks=("not-a-block",))  # type: ignore[arg-type]


class TestParsedDocumentSerialization:
    """序列化往返。"""

    def test_roundtrip(self) -> None:
        original = _parsed_doc()
        restored = ParsedDocument.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_missing_blocks_raises(self) -> None:
        bad = _parsed_doc().to_dict()
        del bad["blocks"]
        with pytest.raises(SerializationError, match="missing key: blocks"):
            ParsedDocument.from_dict(bad)
