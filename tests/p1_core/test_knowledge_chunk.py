"""`KnowledgeChunk` 模型测试。"""

from __future__ import annotations

import pytest

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models.enums import ChunkQuality
from p1_core.models.heading import HeadingPath
from p1_core.models.knowledge_chunk import KnowledgeChunk


def _chunk(**overrides: object) -> KnowledgeChunk:
    """构造默认 `KnowledgeChunk`，可按需覆盖字段。"""
    defaults: dict[str, object] = {
        "chunk_id": "ch-001",
        "raw_doc_id": "01HV3A1B2C3D4E5F6G7H8J9K0L",
        "parsed_doc_id": "parsed-001",
        "heading_path": HeadingPath.root("第 1 章").child("1.1"),
        "text": "本节说明……",
        "page": 1,
        "line_range": (1, 5),
        "parent_chunk_id": None,
        "quality_flag": ChunkQuality.OK,
    }
    defaults.update(overrides)
    return KnowledgeChunk(**defaults)


class TestKnowledgeChunkEquality:
    """相同字段应相等，支持哈希。"""

    def test_equal_when_all_fields_match(self) -> None:
        a = _chunk()
        b = _chunk()
        assert a == b
        assert hash(a) == hash(b)

    def test_unequal_when_quality_differs(self) -> None:
        a = _chunk()
        b = _chunk(quality_flag=ChunkQuality.TOO_SHORT)
        assert a != b


class TestKnowledgeChunkValidation:
    """必填字段校验。"""

    @pytest.mark.parametrize(
        "field",
        ["chunk_id", "raw_doc_id", "parsed_doc_id"],
    )
    def test_blank_id_raises(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _chunk(**{field: ""})

    def test_non_string_text_raises(self) -> None:
        with pytest.raises(ValidationError):
            _chunk(text=123)  # type: ignore[arg-type]

    def test_zero_page_raises(self) -> None:
        with pytest.raises(ValidationError, match="positive int"):
            _chunk(page=0)

    def test_inverted_line_range_raises(self) -> None:
        with pytest.raises(ValidationError, match="1 <= start <= end"):
            _chunk(line_range=(10, 2))

    def test_none_page_and_line_range_allowed(self) -> None:
        chunk = _chunk(page=None, line_range=None, parent_chunk_id=None)
        assert chunk.page is None
        assert chunk.line_range is None
        assert chunk.parent_chunk_id is None


class TestKnowledgeChunkSerialization:
    """序列化往返。"""

    def test_roundtrip_with_parent(self) -> None:
        chunk = _chunk(parent_chunk_id="ch-000")
        restored = KnowledgeChunk.from_dict(chunk.to_dict())
        assert restored == chunk

    def test_roundtrip_without_parent(self) -> None:
        chunk = _chunk(parent_chunk_id=None)
        restored = KnowledgeChunk.from_dict(chunk.to_dict())
        assert restored.parent_chunk_id is None
        assert restored == chunk

    def test_to_dict_contains_heading_path(self) -> None:
        chunk = _chunk()
        data = chunk.to_dict()
        assert "heading_path" in data
        assert "parts" in data["heading_path"]

    def test_from_dict_missing_key_raises(self) -> None:
        bad = _chunk().to_dict()
        del bad["chunk_id"]
        with pytest.raises(SerializationError, match="missing key: chunk_id"):
            KnowledgeChunk.from_dict(bad)

    def test_from_dict_invalid_quality_raises(self) -> None:
        bad = _chunk().to_dict()
        bad["quality_flag"] = "mystery_flag"
        with pytest.raises(SerializationError):
            KnowledgeChunk.from_dict(bad)


class TestKnowledgeChunkHashability:
    """父块/子块关系可哈希化。"""

    def test_chunk_is_hashable(self) -> None:
        chunk = _chunk()
        # 不应抛 TypeError
        assert {chunk, chunk} == {chunk}
