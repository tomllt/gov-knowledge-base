"""`RawDocument` 模型测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument


def _raw_doc(**overrides: object) -> RawDocument:
    """构造默认 `RawDocument`，可按需覆盖字段。"""
    defaults: dict[str, object] = {
        "doc_id": "01HV3A1B2C3D4E5F6G7H8J9K0L",
        "source_type": SourceType.PDF,
        "source_uri": "https://example.local/files/123.pdf",
        "collected_at": datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        "encoding": "utf-8",
        "raw_content": b"%PDF-1.4\n%mock\n",
        "metadata": {"author": "R01", "category": "guide"},
        "access_record_id": "AR-2026-0001",
    }
    defaults.update(overrides)
    return RawDocument(**defaults)


class TestRawDocumentEquality:
    """相同字段应相等，且支持哈希。"""

    def test_equal_when_all_fields_match(self) -> None:
        a = _raw_doc()
        b = _raw_doc()
        assert a == b
        assert hash(a) == hash(b)

    def test_unequal_when_field_differs(self) -> None:
        a = _raw_doc()
        b = _raw_doc(doc_id="OTHER")
        assert a != b

    def test_frozen_blocks_mutation(self) -> None:
        doc = _raw_doc()
        with pytest.raises((AttributeError, Exception)):
            doc.doc_id = "NEW"  # type: ignore[misc]


class TestRawDocumentValidation:
    """空值/类型校验。"""

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_doc_id_raises(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _raw_doc(doc_id=bad)

    def test_blank_source_uri_raises(self) -> None:
        with pytest.raises(ValidationError):
            _raw_doc(source_uri="")

    def test_naive_datetime_raises(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            _raw_doc(collected_at=datetime(2026, 1, 1))

    def test_unsupported_encoding_raises(self) -> None:
        with pytest.raises(ValidationError, match="encoding must be one of"):
            _raw_doc(encoding="ascii")

    def test_non_bytes_raw_content_raises(self) -> None:
        with pytest.raises(ValidationError, match="raw_content must be bytes"):
            _raw_doc(raw_content="not-bytes")  # type: ignore[arg-type]

    def test_invalid_metadata_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be str -> str"):
            _raw_doc(metadata={"k": 1})  # type: ignore[dict-item]

    def test_blank_access_record_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            _raw_doc(access_record_id=" ")


class TestRawDocumentSerialization:
    """序列化往返。"""

    def test_to_dict_keys(self) -> None:
        d = _raw_doc().to_dict()
        expected_keys = {
            "doc_id",
            "source_type",
            "source_uri",
            "collected_at",
            "encoding",
            "raw_content",
            "metadata",
            "access_record_id",
        }
        assert set(d.keys()) == expected_keys

    def test_raw_content_serialized_as_hex(self) -> None:
        doc = _raw_doc(raw_content=b"\xde\xad\xbe\xef")
        assert doc.to_dict()["raw_content"] == "deadbeef"

    def test_roundtrip(self) -> None:
        original = _raw_doc()
        restored = RawDocument.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_missing_key_raises(self) -> None:
        bad = _raw_doc().to_dict()
        del bad["doc_id"]
        with pytest.raises(SerializationError, match="missing key: doc_id"):
            RawDocument.from_dict(bad)

    def test_from_dict_invalid_enum_raises(self) -> None:
        bad = _raw_doc().to_dict()
        bad["source_type"] = "unknown-source"
        with pytest.raises(SerializationError, match="deserialization failed"):
            RawDocument.from_dict(bad)

    def test_from_dict_bad_hex_raises(self) -> None:
        bad = _raw_doc().to_dict()
        bad["raw_content"] = "not-hex"
        with pytest.raises(SerializationError, match="deserialization failed"):
            RawDocument.from_dict(bad)
