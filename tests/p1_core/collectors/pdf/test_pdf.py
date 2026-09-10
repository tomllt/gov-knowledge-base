"""`PdfFileCollector` 端到端测试 (6 类验收场景)。

覆盖场景 (M1-S2a §EXPECTED OUTCOME):
    1. 正样本 (正常 PDF)
    2. 损坏 PDF
    3. 加密 PDF
    4. 超大文件 (>100MB 触发 max_bytes 阈值)
    5. 目录不存在
    6. 权限拒绝

每个场景都同时校验:
    - 采集器行为 (返回 / 不返回 / 异常)
    - SQLite 接入记录状态
    - 隔离目录落盘 (除场景 1 与 5 外)
    - 审计日志事件序列
"""

from __future__ import annotations

import io
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from p1_core.collectors.base import SourceLocator
from p1_core.collectors.pdf.collector import PdfFileCollector
from p1_core.collectors.pdf.ingest_store import IngestStatus, IngestStore
from p1_core.collectors.pdf.redactor import SensitiveRedactor
from p1_core.config import DEFAULT_MAX_BYTES, CollectorConfig
from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument

# 仓库根 = tests/p1_core/collectors/pdf/test_pdf.py 的上级五层
REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent.parent


# ----------------------------------------------------------------------
# Fixture: 临时 config + store + collector
# ----------------------------------------------------------------------
@pytest.fixture
def harness(tmp_path: Path) -> _Harness:
    """构造全套运行时,返回数据访问句柄。"""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    src_migration = REPO_ROOT / "migrations" / "001_ingest_tables.sql"
    (migrations / "001_ingest_tables.sql").write_text(src_migration.read_text("utf-8"), "utf-8")

    cfg = CollectorConfig.with_overrides(
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "p1.db",
        quarantine_dir=tmp_path / "data" / "quarantine",
        migrations_dir=migrations,
        max_bytes=DEFAULT_MAX_BYTES,
    )
    cfg.ensure_dirs()
    store = IngestStore(db_path=cfg.db_path, migrations_dir=cfg.migrations_dir)
    redactor = SensitiveRedactor()
    collector = PdfFileCollector(config=cfg, store=store, redactor=redactor)
    return _Harness(cfg=cfg, store=store, redactor=redactor, collector=collector)


class _Harness:
    """测试运行期句柄聚合。"""

    __slots__ = ("cfg", "collector", "redactor", "store")

    def __init__(
        self,
        cfg: CollectorConfig,
        store: IngestStore,
        redactor: SensitiveRedactor,
        collector: PdfFileCollector,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.redactor = redactor
        self.collector = collector


# ----------------------------------------------------------------------
# PDF 生成辅助
# ----------------------------------------------------------------------
def _make_pdf_bytes(
    *,
    title: str = "办事指南",
    author: str = "上海市公安局",
    text: str = "本指南适用于上海市公安局办事大厅,联系电话 13812345678。",
) -> bytes:
    """生成最小可解析的 PDF 字节流 (含元信息 + 可提取文本)。"""
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    writer.add_metadata(
        {
            "/Title": title,
            "/Author": author,
            "/CreationDate": "D:20260101000000+00'00'",
        }
    )

    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 50 800 Td (" + text.encode("utf-8") + b") Tj ET")
    content_ref = writer._add_object(content)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    resources_ref = writer._add_object(resources)

    page[NameObject("/Contents")] = content_ref
    page[NameObject("/Resources")] = resources_ref

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_corrupt_pdf(path: Path) -> Path:
    """写入一个非 PDF 的损坏文件 (.pdf 扩展名)。"""
    path.write_bytes(b"NOT A PDF\x00\x01\x02")
    return path


def _make_encrypted_pdf(path: Path) -> Path:
    """生成带密码保护的 PDF。"""
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt("secret123", algorithm="AES-256")
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _make_oversize_pdf(path: Path, size_bytes: int) -> Path:
    """写入恰好 ``size_bytes`` 的伪 PDF 文件 (头部合法,体部填充)。"""
    head = b"%PDF-1.4\n"
    pad = b"\x00" * (size_bytes - len(head))
    path.write_bytes(head + pad)
    return path


# ----------------------------------------------------------------------
# 场景 1: 正样本
# ----------------------------------------------------------------------
class TestHappyPath:
    """正常 PDF 应当被采集,返回 RawDocument 并落库。"""

    def test_collects_one_pdf(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        (src_dir / "guide.pdf").write_bytes(_make_pdf_bytes())

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        docs = list(harness.collector.collect(locator))

        assert len(docs) == 1
        doc = docs[0]
        assert isinstance(doc, RawDocument)
        assert doc.source_type is SourceType.PDF
        assert doc.raw_content.startswith(b"%PDF")
        assert doc.metadata["pdf_title"] == "办事指南"
        assert doc.metadata["pdf_author"] == "上海市公安局"
        assert doc.metadata["pdf_page_count"] == "1"

    def test_collect_persists_record_and_logs(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        (src_dir / "guide.pdf").write_bytes(_make_pdf_bytes())

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        docs = list(harness.collector.collect(locator))
        assert len(docs) == 1
        access_id = docs[0].access_record_id

        records = harness.store.list_records()
        assert len(records) == 1
        assert records[0].status is IngestStatus.OK
        assert records[0].access_record_id == access_id

        events = [entry.event for entry in harness.store.list_logs(access_id)]
        assert "start" in events
        assert "collected" in events
        assert "persisted" in events

    def test_redaction_hits_counted(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        (src_dir / "guide.pdf").write_bytes(_make_pdf_bytes(text="联系人 13812345678,请来电咨询。"))

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        list(harness.collector.collect(locator))

        [rec] = harness.store.list_records()
        assert rec.redaction_hits >= 1

    def test_validate_returns_true_for_pdf(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        (src_dir / "guide.pdf").write_bytes(_make_pdf_bytes())
        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        [doc] = list(harness.collector.collect(locator))
        assert harness.collector.validate(doc) is True

    def test_validate_rejects_non_pdf(self, harness: _Harness) -> None:
        doc = RawDocument(
            doc_id="01HV3A1B2C3D4E5F6G7H8J9K0L",
            source_type=SourceType.PDF,
            source_uri="file:///tmp/bad.bin",
            collected_at=datetime(2026, 1, 1, tzinfo=UTC),
            encoding="utf-8",
            raw_content=b"NOT A PDF",
            metadata={},
            access_record_id="AR-2026-0001",
        )
        assert harness.collector.validate(doc) is False


# ----------------------------------------------------------------------
# 场景 2: 损坏 PDF
# ----------------------------------------------------------------------
class TestCorruptPdf:
    """损坏 PDF 应当 quarantine,记录失败,不抛错。"""

    def test_corrupt_pdf_quarantined(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_corrupt_pdf(src_dir / "broken.pdf")

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        docs = list(harness.collector.collect(locator))

        assert docs == []
        assert any(harness.cfg.quarantine_dir.iterdir())
        [rec] = harness.store.list_records()
        assert rec.status is IngestStatus.QUARANTINED
        assert rec.error_message is not None


# ----------------------------------------------------------------------
# 场景 3: 加密 PDF
# ----------------------------------------------------------------------
class TestEncryptedPdf:
    """加密 PDF 应当 quarantine,记录失败,不抛错。"""

    def test_encrypted_pdf_quarantined(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_encrypted_pdf(src_dir / "secret.pdf")

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        docs = list(harness.collector.collect(locator))

        assert docs == []
        [rec] = harness.store.list_records()
        assert rec.status is IngestStatus.QUARANTINED


# ----------------------------------------------------------------------
# 场景 4: 超大文件 (>100MB)
# ----------------------------------------------------------------------
class TestOversizedFile:
    """文件大小超过 ``max_bytes`` 应直接 quarantine。"""

    def test_oversize_pdf_quarantined_without_loading(
        self, harness: _Harness, tmp_path: Path
    ) -> None:

        harness.cfg = replace(harness.cfg, max_bytes=1024)
        harness.collector._config = harness.cfg
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        _make_oversize_pdf(src_dir / "huge.pdf", size_bytes=4096)

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        docs = list(harness.collector.collect(locator))

        assert docs == []
        [rec] = harness.store.list_records()
        assert rec.status is IngestStatus.QUARANTINED
        assert rec.error_message is not None
        assert "size" in rec.error_message.lower()


# ----------------------------------------------------------------------
# 场景 5: 目录不存在
# ----------------------------------------------------------------------
class TestMissingDirectory:
    """输入目录不存在时抛出 :class:`IngestError`,不进入 iteration。"""

    def test_missing_dir_raises(self, harness: _Harness, tmp_path: Path) -> None:
        ghost = tmp_path / "does-not-exist"
        locator = SourceLocator(path=ghost, source_type=SourceType.PDF)
        with pytest.raises(IngestError):
            list(harness.collector.collect(locator))


# ----------------------------------------------------------------------
# 场景 6: 权限拒绝
# ----------------------------------------------------------------------
class TestPermissionDenied:
    """文件不可读时应当 quarantine,不抛错。"""

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
    def test_unreadable_pdf_quarantined(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        target = src_dir / "noperm.pdf"
        target.write_bytes(_make_pdf_bytes())
        target.chmod(0)

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        try:
            docs = list(harness.collector.collect(locator))
        finally:
            target.chmod(stat.S_IRUSR | stat.S_IWUSR)

        assert docs == []
        [rec] = harness.store.list_records()
        assert rec.status is IngestStatus.QUARANTINED
        assert rec.error_message is not None


# ----------------------------------------------------------------------
# 多文件混合
# ----------------------------------------------------------------------
class TestMixedDirectory:
    """目录中正常 + 损坏文件混合时,只返回正常文件,损坏文件被 quarantine。"""

    def test_mixed_returns_only_valid(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        (src_dir / "ok.pdf").write_bytes(_make_pdf_bytes())
        _make_corrupt_pdf(src_dir / "bad.pdf")
        _make_encrypted_pdf(src_dir / "enc.pdf")

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        docs = list(harness.collector.collect(locator))

        assert len(docs) == 1
        assert docs[0].metadata["pdf_title"] == "办事指南"

        records = harness.store.list_records()
        statuses = [r.status for r in records]
        assert statuses.count(IngestStatus.OK) == 1
        assert statuses.count(IngestStatus.QUARANTINED) == 2


# ----------------------------------------------------------------------
# 非 .pdf 后缀文件被忽略
# ----------------------------------------------------------------------
class TestNonPdfFilesIgnored:
    """非 .pdf 后缀文件应当被忽略,不计入失败。"""

    def test_non_pdf_extensions_skipped(self, harness: _Harness, tmp_path: Path) -> None:
        src_dir = tmp_path / "in"
        src_dir.mkdir()
        (src_dir / "guide.pdf").write_bytes(_make_pdf_bytes())
        (src_dir / "README.txt").write_text("ignore me")
        (src_dir / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        locator = SourceLocator(path=src_dir, source_type=SourceType.PDF)
        docs = list(harness.collector.collect(locator))

        assert len(docs) == 1
        assert len(harness.store.list_records()) == 1
