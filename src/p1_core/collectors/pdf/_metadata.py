"""PDF 文件元信息抽取 (pypdf 封装)。

与采集器主类解耦,便于独立测试与未来切换解析栈 (如 pypdfium2)。
所有失败情形均降级为可选字段,绝不抛出。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pypdf import PdfReader

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class PdfMetadata:
    """PDF 元信息采集结果。"""

    title: str
    author: str
    creation_date: datetime | None
    page_count: int
    is_scanned: bool  # 所有页文本均为空视为扫描件


def _safe_text(value: object) -> str:
    """从元信息字段中提取纯文本,失败/缺失时返回空串。"""
    if value is None:
        return ""
    return str(value).strip()


def extract_metadata(path: Path) -> PdfMetadata:
    """读取 PDF 元信息;任何解析异常都降级为空值。"""
    reader = PdfReader(str(path))
    raw_meta = reader.metadata
    title = _safe_text(getattr(raw_meta, "title", "")) if raw_meta else ""
    author = _safe_text(getattr(raw_meta, "author", "")) if raw_meta else ""
    creation = getattr(raw_meta, "creation_date", None) if raw_meta else None
    page_count = len(reader.pages)

    scanned = True
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            scanned = False
            break

    return PdfMetadata(
        title=title,
        author=author,
        creation_date=creation,
        page_count=page_count,
        is_scanned=scanned,
    )


def extract_full_text(path: Path) -> str:
    """拼接所有页的纯文本;任一页失败则该页贡献空串。

    用于脱敏中间件。F02 阶段会重新做结构化解析,此处仅为命中统计。
    """
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts)


def metadata_to_mapping(meta: PdfMetadata) -> Mapping[str, str]:
    """将 :class:`PdfMetadata` 转换为 RawDocument.metadata 兼容的纯字符串映射。"""
    iso = meta.creation_date.isoformat() if meta.creation_date else ""
    return {
        "pdf_title": meta.title,
        "pdf_author": meta.author,
        "pdf_creation_date": iso,
        "pdf_page_count": str(meta.page_count),
        "is_scanned": "true" if meta.is_scanned else "false",
    }


__all__ = ["PdfMetadata", "extract_full_text", "extract_metadata", "metadata_to_mapping"]
