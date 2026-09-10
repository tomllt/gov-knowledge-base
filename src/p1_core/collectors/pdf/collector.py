"""PDF 文件采集器 (M1-S2a 主体实现)。

实现 M1-S1 约定的 :class:`BaseCollector` 接口:

    source_type = SourceType.PDF
    collect(source)  -> Iterator[RawDocument]      # 产出可解析 RawDocument
    validate(doc)    -> bool                        # 校验 PDF 魔数 + 大小
    quarantine(doc, reason) -> Path                 # 隔离到 config.quarantine_dir

采集策略:
    1. 入口目录缺失 -> 抛 :class:`IngestError` (配置错误,应让运维感知);
    2. 单文件失败 (损坏/加密/超大/无权限) -> quarantine + 落库 ``quarantined``,
       不阻断后续采集;
    3. 单文件成功 -> 元信息抽取 + 文本脱敏 -> 落库 ``ok`` -> yield RawDocument;
    4. 非 ``.pdf`` 后缀文件直接跳过,不计入失败。
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import EmptyFileError, PdfReadError

from p1_core.collectors.base import BaseCollector, SourceLocator
from p1_core.collectors.pdf._failures import handle_pdf_failure
from p1_core.collectors.pdf._helpers import (
    emit_success_logs,
    generate_access_record_id,
    quarantine_filename,
    sha256_hex,
)
from p1_core.collectors.pdf._metadata import (
    extract_full_text,
    extract_metadata,
    metadata_to_mapping,
)
from p1_core.collectors.pdf.ingest_store import (
    IngestLog,
    IngestRecord,
    IngestStatus,
    IngestStore,
)
from p1_core.collectors.pdf.redactor import SensitiveRedactor
from p1_core.config import CollectorConfig
from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument
from p1_core.models.time_utils import utcnow

_PDF_HEADER: bytes = b"%PDF-"
_PDF_SUFFIX: str = ".pdf"


class PdfFileCollector(BaseCollector):
    """PDF 文件目录采集器。"""

    source_type = SourceType.PDF
    __slots__ = ("_config", "_redactor", "_store")

    def __init__(
        self,
        *,
        config: CollectorConfig,
        store: IngestStore,
        redactor: SensitiveRedactor,
    ) -> None:
        self._config = config
        self._store = store
        self._redactor = redactor
        self._config.ensure_dirs()

    def collect(self, source: SourceLocator) -> Iterator[RawDocument]:
        """按目录扫描 PDF,逐个产出 RawDocument。

        - 入口目录不存在: 抛 :class:`IngestError`;
        - 单文件失败: quarantine + 持久化失败记录, 不抛错。
        """
        if not source.path.exists():
            msg = f"采集目录不存在: {source.path}"
            raise IngestError(msg)
        if not source.path.is_dir():
            msg = f"采集路径不是目录: {source.path}"
            raise IngestError(msg)

        access_id = generate_access_record_id()
        self._store.log(_start_log(access_id, source.path))
        for pdf_path in sorted(source.path.glob(f"*{_PDF_SUFFIX}")):
            yield from self._collect_one(pdf_path, access_id)

    def validate(self, doc: RawDocument) -> bool:
        """校验 ``doc`` 是否为合法 PDF。"""
        if not doc.raw_content.startswith(_PDF_HEADER):
            return False
        return len(doc.raw_content) <= self._config.max_bytes

    def quarantine(self, doc: RawDocument, reason: str) -> Path:
        """将 ``doc`` 原始字节落盘到隔离目录, 返回落盘后绝对路径。"""
        target = self._config.quarantine_dir / quarantine_filename(Path(doc.source_uri).name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(doc.raw_content)
        return target

    def _collect_one(self, pdf_path: Path, access_id: str) -> Iterator[RawDocument]:
        """处理单个 PDF;失败 -> quarantine, 成功 -> yield RawDocument。"""
        collected_at = utcnow()
        try:
            raw_bytes = pdf_path.read_bytes()
        except (PermissionError, OSError) as exc:
            self._on_failure(
                pdf_path,
                raw_bytes=b"",
                access_id=access_id,
                collected_at=collected_at,
                reason=f"read_failed: {exc}",
            )
            return

        size = len(raw_bytes)
        if size > self._config.max_bytes:
            self._on_failure(
                pdf_path,
                raw_bytes=raw_bytes,
                access_id=access_id,
                collected_at=collected_at,
                reason=f"oversize: {size} > {self._config.max_bytes}",
            )
            return

        if not raw_bytes.startswith(_PDF_HEADER):
            self._on_failure(
                pdf_path,
                raw_bytes=raw_bytes,
                access_id=access_id,
                collected_at=collected_at,
                reason="bad_magic: not a PDF",
            )
            return

        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
            if reader.is_encrypted:
                self._on_failure(
                    pdf_path,
                    raw_bytes=raw_bytes,
                    access_id=access_id,
                    collected_at=collected_at,
                    reason="encrypted_pdf",
                )
                return
            meta = extract_metadata(pdf_path)
            text = extract_full_text(pdf_path)
        except (PdfReadError, EmptyFileError, ValueError, OSError) as exc:
            self._on_failure(
                pdf_path,
                raw_bytes=raw_bytes,
                access_id=access_id,
                collected_at=collected_at,
                reason=f"parse_failed: {exc}",
            )
            return

        redaction = self._redactor.redact(text)
        sha = sha256_hex(raw_bytes)
        doc_id = uuid.uuid4().hex
        metadata = dict(metadata_to_mapping(meta))
        metadata["redaction_hits"] = str(redaction.hits)
        metadata["redaction_counts"] = ",".join(
            f"{k}={v}" for k, v in sorted(redaction.counts.items())
        )
        doc = RawDocument(
            doc_id=doc_id,
            source_type=SourceType.PDF,
            source_uri=str(pdf_path),
            collected_at=collected_at,
            encoding="utf-8",
            raw_content=raw_bytes,
            metadata=metadata,
            access_record_id=access_id,
        )
        emit_success_logs(
            store=self._store,
            access_id=access_id,
            pdf_path=pdf_path,
            size=size,
            redaction_hits=redaction.hits,
            doc_id=doc_id,
        )
        self._store.record(
            IngestRecord(
                access_record_id=access_id,
                source_type=SourceType.PDF.value,
                source_uri=str(pdf_path),
                doc_id=doc_id,
                sha256=sha,
                size_bytes=size,
                encoding="utf-8",
                collected_at=collected_at,
                status=IngestStatus.OK,
                error_message=None,
                quarantine_path=None,
                redaction_hits=redaction.hits,
            )
        )
        yield doc

    def _on_failure(
        self,
        pdf_path: Path,
        *,
        raw_bytes: bytes,
        access_id: str,
        collected_at: datetime,
        reason: str,
    ) -> None:
        """隔离 + 落库失败记录;不抛错。"""
        handle_pdf_failure(
            pdf_path_name=str(pdf_path),
            raw_bytes=raw_bytes,
            access_id=access_id,
            collected_at=collected_at,
            reason=reason,
            config=self._config,
            store=self._store,
        )


def _start_log(access_id: str, input_dir: Path) -> IngestLog:
    """构造采集开始事件日志。"""
    return IngestLog(
        access_record_id=access_id,
        event="start",
        level="info",
        detail=f"input_dir={input_dir}",
    )


__all__ = ["PdfFileCollector"]
