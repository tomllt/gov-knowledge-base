"""PDF 文件采集器公共 API。"""

from p1_core.collectors.pdf.collector import PdfFileCollector
from p1_core.collectors.pdf.ingest_store import (
    IngestLog,
    IngestRecord,
    IngestStatus,
    IngestStore,
)
from p1_core.collectors.pdf.redactor import RedactionResult, SensitiveRedactor

__all__ = [
    "IngestLog",
    "IngestRecord",
    "IngestStatus",
    "IngestStore",
    "PdfFileCollector",
    "RedactionResult",
    "SensitiveRedactor",
]
