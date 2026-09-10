"""PDF 采集模块的运行时辅助函数。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from p1_core.collectors.pdf.ingest_store import IngestLog
from p1_core.models.time_utils import utcnow

if TYPE_CHECKING:
    from p1_core.collectors.pdf.ingest_store import IngestStore


def sha256_hex(data: bytes) -> str:
    """计算 ``data`` 的 SHA-256 十六进制摘要。"""
    return hashlib.sha256(data).hexdigest()


def generate_access_record_id() -> str:
    """生成形如 ``AR-YYYYMMDD-xxxxxxxx`` 的接入单号。"""
    return f"AR-{utcnow():%Y%m%d}-{uuid.uuid4().hex[:8]}"


def quarantine_filename(src_name: str) -> str:
    """为隔离文件生成唯一文件名。"""
    return f"{src_name or 'unknown.pdf'}.{uuid.uuid4().hex[:8]}.pdf"


def emit_success_logs(
    *,
    store: IngestStore,
    access_id: str,
    pdf_path: Path,
    size: int,
    redaction_hits: int,
    doc_id: str,
) -> None:
    """写入成功相关审计日志。"""

    events = (
        ("collected", f"path={pdf_path} size={size}"),
        ("validated", "pdf_magic_ok"),
        ("redacted", f"hits={redaction_hits}"),
        ("persisted", f"doc_id={doc_id}"),
    )
    for event, detail in events:
        store.log(IngestLog(access_id, event, "info", detail))


__all__ = ["emit_success_logs", "generate_access_record_id", "quarantine_filename", "sha256_hex"]
