"""PDF 采集失败处理模块。

单文件失败 (损坏/加密/超大/无权限) 的统一处理流程:
    1. 隔离原始字节到 quarantine_dir;
    2. 写入 ``ingest_record`` (status=QUARANTINED);
    3. 写入 ``ingest_log`` (failed / quarantined);
    4. 不抛错,不阻断后续文件。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from p1_core.collectors.pdf._helpers import quarantine_filename, sha256_hex
from p1_core.collectors.pdf.ingest_store import (
    IngestLog,
    IngestRecord,
    IngestStatus,
    IngestStore,
)
from p1_core.config import CollectorConfig
from p1_core.models.enums import SourceType


def handle_pdf_failure(
    *,
    pdf_path_name: str,
    raw_bytes: bytes,
    access_id: str,
    collected_at: datetime,
    reason: str,
    config: CollectorConfig,
    store: IngestStore,
) -> None:
    """隔离 + 落库失败记录;不抛错,不返回任何值。"""
    sha = sha256_hex(raw_bytes) if raw_bytes else ""
    size = len(raw_bytes)

    quarantine_rel: str | None = None
    if raw_bytes:
        target = config.quarantine_dir / quarantine_filename(Path(pdf_path_name).name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw_bytes)
        quarantine_rel = str(target.relative_to(config.data_dir))

    doc_id = uuid.uuid4().hex
    store.record(
        IngestRecord(
            access_record_id=f"{access_id}:{doc_id[:8]}",
            source_type=SourceType.PDF.value,
            source_uri=pdf_path_name,
            doc_id=doc_id,
            sha256=sha,
            size_bytes=size,
            encoding="utf-8",
            collected_at=collected_at,
            status=IngestStatus.QUARANTINED,
            error_message=reason,
            quarantine_path=quarantine_rel,
            redaction_hits=0,
        )
    )
    store.log(
        IngestLog(
            access_record_id=access_id,
            event="failed",
            level="warning",
            detail=f"reason={reason} path={pdf_path_name}",
        )
    )
    if quarantine_rel is not None:
        store.log(
            IngestLog(
                access_record_id=access_id,
                event="quarantined",
                level="warning",
                detail=quarantine_rel,
            )
        )


__all__ = ["handle_pdf_failure"]
