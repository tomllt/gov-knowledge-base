"""`WordFileCollector` 测试。

覆盖以下六类场景（与 issue 验收一致）：
  1. 正样本（含段落 + 表格）
  2. 损坏文件（截断 zip）
  3. 加密 docx（zip 结构但 document.xml 不可解析，模拟加密包）
  4. 空文件
  5. 旧二进制 .doc（应标记 unsupported_format）
  6. 巨文件（确保大文件可被采集）
"""

from __future__ import annotations

import io
import secrets
import zipfile
from pathlib import Path

import pytest
from docx import Document as DocxDocument

from p1_core.collectors.base import UnsupportedFormatError
from p1_core.collectors.document import WordFileCollector
from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument


def _make_docx_bytes(
    *,
    paragraphs: list[str] | None = None,
    tables: list[list[list[str]]] | None = None,
) -> bytes:
    """使用 python-docx 构造真实 .docx 字节流，便于在内存中复用。"""
    buf = io.BytesIO()
    doc = DocxDocument()
    for text in paragraphs or []:
        doc.add_paragraph(text)
    for table in tables or []:
        rows = len(table)
        cols = max((len(row) for row in table), default=1)
        t = doc.add_table(rows=rows, cols=cols)
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    doc.save(buf)
    return buf.getvalue()


def _make_encrypted_like_docx() -> bytes:
    """模拟加密 docx：合法 zip 但 document.xml 为乱码，python-docx 无法解析。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package'
            '.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        zf.writestr("word/_rels/document.xml.rels", "<garbled/>")
        zf.writestr("word/document.xml", "<garbled/>")
    return buf.getvalue()


def _make_truncated_docx() -> bytes:
    """截断的合法 docx 字节：zip header 完好但 central directory 缺失。"""
    full = _make_docx_bytes(paragraphs=["abc"])
    # zip local file header 通常 30 bytes + 文件名长度 + 至少部分数据；
    # 截断后 central directory 缺失导致 zipfile 报错。
    return full[: max(64, len(full) // 4)]


class TestWordFileCollectorMetadata:
    """采集器元信息与接口契约。"""

    def test_source_type_is_word(self) -> None:
        assert WordFileCollector.source_type is SourceType.WORD

    def test_supported_extensions_includes_docx_doc(self) -> None:
        exts = WordFileCollector().supported_extensions()
        assert ".docx" in exts
        assert ".doc" in exts


class TestWordFileCollectorHappyPath:
    """正样本：合法 .docx 解析 + 元信息提取。"""

    def test_collects_real_docx_with_paragraphs_and_tables(self, tmp_path: Path) -> None:
        payload = _make_docx_bytes(
            paragraphs=["标题一", "正文段落"],
            tables=[[["表头1", "表头2"], ["数据1", "数据2"]]],
        )
        path = tmp_path / "sample.docx"
        path.write_bytes(payload)

        result = WordFileCollector().collect(path)

        assert isinstance(result, RawDocument)
        assert result.source_type is SourceType.WORD
        assert result.source_uri == str(path)
        assert result.encoding == "utf-8"
        assert result.raw_content == payload
        # OOXML 版本：python-docx 默认写入 ECMA-376 2006 兼容标识。
        assert "ooxml_version" in result.metadata
        assert result.metadata["ooxml_version"]  # non-empty
        assert result.metadata["paragraph_count"] == "2"
        assert result.metadata["table_count"] == "1"
        assert result.metadata["table_row_count"] == "2"
        assert result.metadata["table_column_count"] == "2"
        # doc_id 与 access_record_id 必须为非空字符串。
        assert result.doc_id
        assert result.access_record_id
        # 时间戳必须带时区。
        assert result.collected_at.tzinfo is not None

    def test_collects_docx_without_tables(self, tmp_path: Path) -> None:
        payload = _make_docx_bytes(paragraphs=["only paragraph"])
        path = tmp_path / "no-table.docx"
        path.write_bytes(payload)

        result = WordFileCollector().collect(path)

        assert result.metadata["paragraph_count"] == "1"
        assert result.metadata["table_count"] == "0"

    def test_doc_id_is_stable_per_file(self, tmp_path: Path) -> None:
        payload = _make_docx_bytes(paragraphs=["x"])
        path = tmp_path / "stable.docx"
        path.write_bytes(payload)
        collector = WordFileCollector()
        first = collector.collect(path)
        second = collector.collect(path)
        assert first.doc_id == second.doc_id
        assert first.access_record_id == second.access_record_id


class TestWordFileCollectorErrorScenarios:
    """异常路径：损坏 / 加密 / 空文件 / 旧二进制 .doc。"""

    def test_corrupted_docx_raises_ingest_error(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.docx"
        path.write_bytes(_make_truncated_docx())
        with pytest.raises(IngestError, match=r"corrupted|truncated|invalid"):
            WordFileCollector().collect(path)

    def test_encrypted_docx_raises_ingest_error(self, tmp_path: Path) -> None:
        path = tmp_path / "secret.docx"
        path.write_bytes(_make_encrypted_like_docx())
        with pytest.raises(IngestError, match=r"encrypted|invalid|unreadable"):
            WordFileCollector().collect(path)

    def test_empty_file_raises_ingest_error(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.docx"
        path.write_bytes(b"")
        with pytest.raises(IngestError, match=r"empty"):
            WordFileCollector().collect(path)

    def test_legacy_doc_raises_unsupported_format_error(self, tmp_path: Path) -> None:
        path = tmp_path / "legacy.doc"
        path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")  # OLE2 magic bytes
        with pytest.raises(UnsupportedFormatError, match=r"unsupported_format"):
            WordFileCollector().collect(path)

    def test_missing_file_raises_ingest_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost.docx"
        with pytest.raises(IngestError, match=r"not found|missing|no such"):
            WordFileCollector().collect(missing)


class TestWordFileCollectorLargeFile:
    """巨文件：保证采集器不会因内存或时间问题崩溃。"""

    def test_collects_large_docx(self, tmp_path: Path) -> None:
        # 生成不可压缩的大 docx：每段唯一随机内容，确保 zip 压缩率低。
        big_paragraphs = [secrets.token_hex(512) for _ in range(20000)]
        payload = _make_docx_bytes(paragraphs=big_paragraphs)
        path = tmp_path / "big.docx"
        path.write_bytes(payload)
        # 仅断言远大于内存基线（10 MB），不强求精确 5 MB。
        assert path.stat().st_size >= 10 * 1024 * 1024

        result = WordFileCollector().collect(path)

        assert result.metadata["paragraph_count"] == "20000"
        assert len(result.raw_content) == path.stat().st_size


class TestWordFileCollectorDirectoryIteration:
    """目录批量采集 + 错误隔离。"""

    def test_iter_directory_picks_supported_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "a.docx").write_bytes(_make_docx_bytes(paragraphs=["a"]))
        (tmp_path / "b.docx").write_bytes(_make_docx_bytes(paragraphs=["b"]))
        (tmp_path / "skip.txt").write_text("plain", encoding="utf-8")

        results = list(WordFileCollector().iter_directory(tmp_path))

        assert len(results) == 2
        assert all(isinstance(r, RawDocument) for r in results)

    def test_iter_directory_isolates_legacy_doc_as_unsupported(self, tmp_path: Path) -> None:
        (tmp_path / "ok.docx").write_bytes(_make_docx_bytes(paragraphs=["ok"]))
        (tmp_path / "legacy.doc").write_bytes(b"\xd0\xcf\x11\xe0")

        results = list(WordFileCollector().iter_directory(tmp_path))

        kinds = [type(r).__name__ for r in results]
        assert "RawDocument" in kinds
        assert "UnsupportedFormatError" in kinds
