"""P1-F02 解析器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from p1_core.exceptions import ParseError
from p1_core.models.enums import DocumentFormat, SourceType
from p1_core.models.parsed_document import ParsedDocument
from p1_core.models.raw_document import RawDocument

_SOURCE_TYPES: dict[DocumentFormat, frozenset[SourceType]] = {
    DocumentFormat.HTML: frozenset({SourceType.HTML}),
    DocumentFormat.PDF: frozenset({SourceType.PDF}),
    DocumentFormat.DOCX: frozenset({SourceType.WORD}),
    DocumentFormat.TEXT: frozenset(
        {
            SourceType.API,
            SourceType.DATABASE,
            SourceType.TICKET_12345,
            SourceType.MANUAL,
            SourceType.HTML,
            SourceType.PDF,
            SourceType.WORD,
        }
    ),
}


class BaseParser(ABC):
    """P1-F02 知识解析器的最小公共接口。"""

    format: ClassVar[DocumentFormat]

    @abstractmethod
    def parse(self, raw: RawDocument) -> ParsedDocument:
        """将单份原始文档解析为结构化文档。"""
        ...

    def _ensure_format(self, raw: RawDocument) -> None:
        """拒绝来源格式与当前解析器不匹配的文档。"""
        expected = _SOURCE_TYPES.get(self.format)
        if expected is not None and raw.source_type not in expected:
            msg = (
                f"parser format {self.format.value!r} does not accept "
                f"source_type {raw.source_type.value!r}; "
                f"expected one of {sorted(item.value for item in expected)}"
            )
            raise ParseError(msg)


__all__ = ["BaseParser"]
