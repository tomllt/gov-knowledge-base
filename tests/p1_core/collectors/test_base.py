"""`BaseCollector` 与 `SourceLocator` 接口契约测试。

约束来源:GOV-1 / M1-S1 骨架约定的采集器协议。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p1_core.collectors.base import BaseCollector, SourceLocator
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument


def _raw_doc(**overrides: object) -> RawDocument:
    defaults: dict[str, object] = {
        "doc_id": "01HV3A1B2C3D4E5F6G7H8J9K0L",
        "source_type": SourceType.PDF,
        "source_uri": "https://example.local/files/123.pdf",
        "collected_at": datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        "encoding": "utf-8",
        "raw_content": b"%PDF-1.4\n",
        "metadata": {},
        "access_record_id": "AR-2026-0001",
    }
    defaults.update(overrides)
    return RawDocument(**defaults)


class TestSourceLocator:
    """`SourceLocator` 应是不可变的源定位描述。"""

    def test_required_fields(self, tmp_path: Path) -> None:
        loc = SourceLocator(path=tmp_path, source_type=SourceType.PDF)
        assert loc.path == tmp_path
        assert loc.source_type == SourceType.PDF

    def test_frozen_blocks_mutation(self, tmp_path: Path) -> None:
        loc = SourceLocator(path=tmp_path, source_type=SourceType.PDF)
        with pytest.raises((AttributeError, Exception)):
            loc.path = tmp_path / "other.pdf"  # type: ignore[misc]

    def test_non_path_rejected(self) -> None:
        with pytest.raises(TypeError, match="path"):
            SourceLocator(path="/tmp/anything.pdf", source_type=SourceType.PDF)  # type: ignore[arg-type]


class TestBaseCollectorContract:
    """`BaseCollector` 必须强制实现三个抽象方法。"""

    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseCollector()  # type: ignore[abstract]

    def test_subclass_missing_methods_rejected(self) -> None:
        class Incomplete(BaseCollector):
            source_type = SourceType.PDF

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_subclass_with_all_methods_accepted(self, tmp_path: Path) -> None:
        class Stub(BaseCollector):
            source_type = SourceType.PDF

            def collect(self, source: SourceLocator) -> Iterator[RawDocument]:
                yield _raw_doc(source_uri=str(source.path))

            def validate(self, doc: RawDocument) -> bool:
                return bool(doc.raw_content)

            def quarantine(self, doc: RawDocument, reason: str) -> Path:
                target = tmp_path / "quar.bin"
                target.write_bytes(doc.raw_content)
                return target

        stub = Stub()
        assert stub.source_type is SourceType.PDF

        loc = SourceLocator(path=tmp_path / "in.pdf", source_type=SourceType.PDF)
        docs = list(stub.collect(loc))
        assert len(docs) == 1
        assert stub.validate(docs[0]) is True
        quar = stub.quarantine(docs[0], "test")
        assert quar.exists()
