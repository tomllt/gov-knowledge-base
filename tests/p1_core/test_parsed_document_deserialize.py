"""`ParsedDocument.from_dict` 与 `_parse_block` 反序列化分支测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models.enums import BlockType, DocumentFormat
from p1_core.models.heading import HeadingPath
from p1_core.models.parsed_document import ParsedBlock, ParsedDocument


def _good_parsed_dict() -> dict[str, object]:
    return {
        "raw_doc_id": "raw-001",
        "parsed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "format": DocumentFormat.PDF.value,
        "blocks": [
            {
                "block_id": "b1",
                "block_type": BlockType.PARAGRAPH.value,
                "text": "内容",
                "page": 1,
                "line_range": [1, 5],
                "heading_path": {"parts": ["第 1 章"]},
            }
        ],
    }


class TestParsedDocumentFromDict:
    """`ParsedDocument.from_dict` 反序列化分支。"""

    def test_roundtrip(self) -> None:
        original = ParsedDocument(
            raw_doc_id="raw-001",
            parsed_at=datetime(2026, 1, 1, tzinfo=UTC),
            format=DocumentFormat.PDF,
            blocks=(
                ParsedBlock(
                    block_id="b1",
                    block_type=BlockType.PARAGRAPH,
                    text="内容",
                    page=1,
                    line_range=(1, 5),
                    heading_path=HeadingPath.root("第 1 章"),
                ),
            ),
        )
        restored = ParsedDocument.from_dict(original.to_dict())
        assert restored == original

    def test_blocks_not_sequence_raises(self) -> None:
        bad = _good_parsed_dict()
        bad["blocks"] = 42  # int 非 Sequence
        with pytest.raises(SerializationError, match="must be Sequence"):
            ParsedDocument.from_dict(bad)

    def test_blocks_item_not_mapping_raises(self) -> None:
        bad = _good_parsed_dict()
        bad["blocks"] = ["not-a-mapping"]
        with pytest.raises(SerializationError, match="must be Mapping"):
            ParsedDocument.from_dict(bad)

    def test_block_with_invalid_page_type_raises(self) -> None:
        bad = _good_parsed_dict()
        block = bad["blocks"]
        assert isinstance(block, list)
        block[0]["page"] = "1"  # type: ignore[index]
        with pytest.raises(SerializationError, match=r"block.page must be int"):
            ParsedDocument.from_dict(bad)

    def test_block_with_invalid_line_range_raises(self) -> None:
        bad = _good_parsed_dict()
        block = bad["blocks"]
        assert isinstance(block, list)
        block[0]["line_range"] = "not-a-pair"  # type: ignore[index]
        with pytest.raises(SerializationError, match=r"block.line_range must be \(int, int\)"):
            ParsedDocument.from_dict(bad)

    def test_block_with_string_line_range_raises(self) -> None:
        bad = _good_parsed_dict()
        block = bad["blocks"]
        assert isinstance(block, list)
        block[0]["line_range"] = ["1", "2"]  # type: ignore[index]
        with pytest.raises(SerializationError, match=r"block.line_range entries must be int"):
            ParsedDocument.from_dict(bad)

    def test_block_with_invalid_heading_path_raises(self) -> None:
        bad = _good_parsed_dict()
        block = bad["blocks"]
        assert isinstance(block, list)
        block[0]["heading_path"] = "not-a-mapping"  # type: ignore[index]
        with pytest.raises(SerializationError, match=r"block.heading_path must be Mapping"):
            ParsedDocument.from_dict(bad)

    def test_from_dict_with_none_page_and_line_range(self) -> None:
        good = _good_parsed_dict()
        block = good["blocks"]
        assert isinstance(block, list)
        block[0]["page"] = None  # type: ignore[index]
        block[0]["line_range"] = None  # type: ignore[index]
        block[0]["heading_path"] = None  # type: ignore[index]
        pd = ParsedDocument.from_dict(good)
        assert pd.blocks[0].page is None
        assert pd.blocks[0].line_range is None
        assert pd.blocks[0].heading_path is None


class TestParsedDocumentConstructionEdgeCases:
    """`ParsedDocument.__post_init__` 边界条件。"""

    def test_blocks_with_non_parsed_block_raises(self) -> None:
        with pytest.raises(ValidationError, match=r"blocks\[0\] must be ParsedBlock"):
            ParsedDocument(
                raw_doc_id="x",
                parsed_at=datetime(2026, 1, 1, tzinfo=UTC),
                format=DocumentFormat.PDF,
                blocks=("not-a-block",),  # type: ignore[arg-type]
            )


@pytest.mark.parametrize("field", ["raw_doc_id", "parsed_at", "format"])
def test_required_document_strings_reject_non_strings(field: str) -> None:
    bad = _good_parsed_dict()
    bad[field] = 123
    with pytest.raises(SerializationError, match=f"{field} must be str"):
        ParsedDocument.from_dict(bad)


@pytest.mark.parametrize("field", ["block_id", "block_type", "text"])
def test_required_block_strings_reject_non_strings(field: str) -> None:
    bad = _good_parsed_dict()
    blocks = bad["blocks"]
    assert isinstance(blocks, list)
    block = blocks[0]
    assert isinstance(block, dict)
    block[field] = 123
    with pytest.raises(SerializationError, match=f"{field} must be str"):
        ParsedDocument.from_dict(bad)


def test_invalid_page_and_warning_collections_raise() -> None:
    bad = _good_parsed_dict()
    bad["pages"] = "invalid"
    with pytest.raises(SerializationError, match="invalid document collections"):
        ParsedDocument.from_dict(bad)
    bad = _good_parsed_dict()
    bad["parse_warnings"] = "invalid"
    with pytest.raises(SerializationError, match="invalid document collections"):
        ParsedDocument.from_dict(bad)


def test_invalid_metadata_and_table_cells_raise() -> None:
    bad = _good_parsed_dict()
    bad["metadata"] = {"source": 1}
    with pytest.raises(SerializationError, match="metadata"):
        ParsedDocument.from_dict(bad)
    bad = _good_parsed_dict()
    bad["pages"] = [{"page_num": 1, "text": "", "tables": [{"rows": [[1]]}]}]
    with pytest.raises(SerializationError, match="table cells"):
        ParsedDocument.from_dict(bad)


@pytest.mark.parametrize("field", ["pages", "parse_warnings"])
def test_document_collection_entries_must_be_mappings(field: str) -> None:
    bad = _good_parsed_dict()
    bad[field] = ["not-a-mapping"]
    with pytest.raises(SerializationError, match="must be Mapping"):
        ParsedDocument.from_dict(bad)
