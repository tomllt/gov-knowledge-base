"""`BaseCollector` 与 `UnsupportedFormatError` 测试。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

import pytest

from p1_core.collectors.base import BaseCollector, UnsupportedFormatError
from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument


class _StubCollector(BaseCollector):
    """用于基类行为测试的桩采集器（不解析真实文件格式）。"""

    source_type: ClassVar[SourceType] = SourceType.PDF
    extra_extensions: ClassVar[frozenset[str]] = frozenset()

    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".txt"}) | self.extra_extensions

    def collect(self, path: Path) -> RawDocument:
        if path.suffix.lower() == ".unsupported":
            msg = f"unsupported: {path}"
            raise UnsupportedFormatError(msg)
        if path.suffix.lower() == ".broken":
            msg = f"broken: {path}"
            raise IngestError(msg)
        return _make_raw_doc(path)


def _make_raw_doc(path: Path) -> RawDocument:
    return RawDocument(
        doc_id=path.stem,
        source_type=SourceType.PDF,
        source_uri=str(path),
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        encoding="utf-8",
        raw_content=b"hello",
        metadata=MappingProxyType({"name": path.name}),
        access_record_id="AR-1",
    )


class TestUnsupportedFormatError:
    """自定义异常层级。"""

    def test_is_ingest_error_subclass(self) -> None:
        assert issubclass(UnsupportedFormatError, IngestError)

    def test_is_raisable(self) -> None:
        with pytest.raises(UnsupportedFormatError, match=r"legacy"):
            raise UnsupportedFormatError("legacy doc is not supported")  # noqa: TRY003


class TestBaseCollectorInterface:
    """抽象接口与批量入口。"""

    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            BaseCollector()  # type: ignore[abstract]

    def test_supported_extensions_returns_frozenset(self) -> None:
        exts = _StubCollector().supported_extensions()
        assert isinstance(exts, frozenset)
        assert ".txt" in exts

    def test_iter_directory_filters_by_extension(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.bin").write_bytes(b"\x00")
        results = list(_StubCollector().iter_directory(tmp_path))
        assert len(results) == 1
        assert isinstance(results[0], RawDocument)
        assert results[0].doc_id == "a"

    def test_iter_directory_yields_ingest_error_for_broken_file(self, tmp_path: Path) -> None:
        # `.broken` 必须先注册到 supported_extensions，否则会被扩展名过滤掉。
        collector = _StubCollector()
        collector.extra_extensions = frozenset({".broken"})
        (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
        (tmp_path / "bad.broken").write_text("bad", encoding="utf-8")
        results = list(collector.iter_directory(tmp_path))
        kinds = [type(r).__name__ for r in results]
        assert "RawDocument" in kinds
        assert "IngestError" in kinds

    def test_iter_directory_yields_unsupported_format_error(self, tmp_path: Path) -> None:
        collector = _StubCollector()
        collector.extra_extensions = frozenset({".unsupported"})
        (tmp_path / "legacy.unsupported").write_text("x", encoding="utf-8")
        results = list(collector.iter_directory(tmp_path))
        assert len(results) == 1
        assert isinstance(results[0], UnsupportedFormatError)

    def test_iter_directory_raises_when_path_is_not_dir(self, tmp_path: Path) -> None:
        not_dir = tmp_path / "missing"
        with pytest.raises(IngestError, match=r"not a directory"):
            list(_StubCollector().iter_directory(not_dir))

    def test_iter_directory_recursive(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested"
        nested.mkdir(parents=True)
        (tmp_path / "top.txt").write_text("t", encoding="utf-8")
        (nested / "inner.txt").write_text("i", encoding="utf-8")
        flat = list(_StubCollector().iter_directory(tmp_path))
        recursive = list(_StubCollector().iter_directory(tmp_path, recursive=True))
        assert len(flat) == 1
        assert len(recursive) == 2

    def test_collect_directory_drops_errors(self, tmp_path: Path) -> None:
        collector = _StubCollector()
        collector.extra_extensions = frozenset({".broken"})
        (tmp_path / "ok.txt").write_text("o", encoding="utf-8")
        (tmp_path / "bad.broken").write_text("b", encoding="utf-8")
        docs = collector.collect_directory(tmp_path)
        assert all(isinstance(d, RawDocument) for d in docs)
        assert len(docs) == 1


# 锁定公共 re-export 名称（Iterable 在 base.py 中已声明）。
_ = Iterable
