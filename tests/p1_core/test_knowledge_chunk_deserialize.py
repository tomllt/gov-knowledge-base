"""`KnowledgeChunk.from_dict` 反序列化分支测试。"""

from __future__ import annotations

import pytest

from p1_core.exceptions import SerializationError
from p1_core.models.enums import ChunkQuality
from p1_core.models.heading import HeadingPath
from p1_core.models.knowledge_chunk import KnowledgeChunk
from p1_core.models.raw_document import RawDocument


def _good_chunk_dict() -> dict[str, object]:
    return {
        "chunk_id": "ch-001",
        "raw_doc_id": "raw-001",
        "parsed_doc_id": "parsed-001",
        "heading_path": {"parts": ["第 1 章"]},
        "text": "正文",
        "page": 1,
        "line_range": [1, 5],
        "parent_chunk_id": None,
        "quality_flag": ChunkQuality.OK.value,
    }


class TestKnowledgeChunkFromDict:
    """`KnowledgeChunk.from_dict` 反序列化分支。"""

    def test_roundtrip(self) -> None:
        chunk = KnowledgeChunk(
            chunk_id="ch-001",
            raw_doc_id="raw-001",
            parsed_doc_id="parsed-001",
            heading_path=HeadingPath.root("第 1 章"),
            text="正文",
            page=1,
            line_range=(1, 5),
            parent_chunk_id=None,
            quality_flag=ChunkQuality.OK,
        )
        restored = KnowledgeChunk.from_dict(chunk.to_dict())
        assert restored == chunk

    def test_missing_heading_path_raises(self) -> None:
        bad = _good_chunk_dict()
        del bad["heading_path"]
        with pytest.raises(SerializationError, match="missing key: heading_path"):
            KnowledgeChunk.from_dict(bad)

    def test_invalid_heading_path_raises(self) -> None:
        bad = _good_chunk_dict()
        bad["heading_path"] = "not-a-mapping"
        with pytest.raises(SerializationError, match="must be Mapping"):
            KnowledgeChunk.from_dict(bad)

    def test_invalid_quality_raises(self) -> None:
        bad = _good_chunk_dict()
        bad["quality_flag"] = "mystery"
        with pytest.raises(SerializationError):
            KnowledgeChunk.from_dict(bad)

    def test_invalid_page_type_raises(self) -> None:
        bad = _good_chunk_dict()
        bad["page"] = "1"
        with pytest.raises(SerializationError, match="page must be int"):
            KnowledgeChunk.from_dict(bad)

    def test_invalid_line_range_length_raises(self) -> None:
        bad = _good_chunk_dict()
        bad["line_range"] = [1, 2, 3]
        with pytest.raises(SerializationError, match=r"line_range must be \(int, int\)"):
            KnowledgeChunk.from_dict(bad)

    def test_invalid_line_range_entry_raises(self) -> None:
        bad = _good_chunk_dict()
        bad["line_range"] = ["1", "2"]
        with pytest.raises(SerializationError, match="line_range entries must be int"):
            KnowledgeChunk.from_dict(bad)

    def test_invalid_parent_chunk_id_raises(self) -> None:
        bad = _good_chunk_dict()
        bad["parent_chunk_id"] = 42
        with pytest.raises(SerializationError, match="parent_chunk_id must be str or None"):
            KnowledgeChunk.from_dict(bad)

    def test_from_dict_with_string_line_range_raises(self) -> None:
        bad = _good_chunk_dict()
        bad["line_range"] = "not a sequence"
        with pytest.raises(SerializationError, match=r"line_range must be \(int, int\)"):
            KnowledgeChunk.from_dict(bad)


class TestRawDocumentFromDictEdge:
    """`RawDocument.from_dict` 反序列化分支。"""

    def test_missing_field_raises(self) -> None:
        bad: dict[str, object] = {
            "doc_id": "x",
            "source_type": "pdf",
            "source_uri": "u",
            "collected_at": "2026-01-01T00:00:00+00:00",
            "encoding": "utf-8",
            "raw_content": "00",
            # access_record_id 缺失
        }
        with pytest.raises(SerializationError, match="missing key: access_record_id"):
            RawDocument.from_dict(bad)

    def test_invalid_metadata_type_raises(self) -> None:
        bad: dict[str, object] = {
            "doc_id": "x",
            "source_type": "pdf",
            "source_uri": "u",
            "collected_at": "2026-01-01T00:00:00+00:00",
            "encoding": "utf-8",
            "raw_content": "00",
            "access_record_id": "AR-1",
            "metadata": ["not", "a", "mapping"],
        }
        with pytest.raises(SerializationError, match="must be Mapping"):
            RawDocument.from_dict(bad)
