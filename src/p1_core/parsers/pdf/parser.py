"""Offline PDF parsing with bounded extraction and injectable OCR."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Protocol

import pdfplumber
import pypdfium2 as pdfium

from p1_core.exceptions import ParseError
from p1_core.models.enums import BlockType, DocumentFormat
from p1_core.models.parsed_document import (
    ParsedBlock,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    ParseWarning,
)
from p1_core.models.raw_document import RawDocument
from p1_core.parsers.pdf.runtime import render_page_with_size, run_document, run_ocr


class OCRFunction(Protocol):
    def __call__(self, page: bytes, page_num: int) -> str: ...


@dataclass(frozen=True, slots=True)
class PdfParserLimits:
    max_pages: int = 500
    max_bytes: int = 50_000_000
    max_page_pixels: int = 25_000_000
    max_dimension: int = 10_000
    max_ocr_bytes: int = 10_000_000
    max_dpi: int = 200

    def __post_init__(self) -> None:
        values = (
            self.max_pages,
            self.max_bytes,
            self.max_page_pixels,
            self.max_dimension,
            self.max_dpi,
        )
        if any(value <= 0 for value in values):
            raise ValueError("PDF limits must be positive")
        if self.max_ocr_bytes <= 0:
            raise ValueError("max_ocr_bytes must be positive")


@dataclass(frozen=True, slots=True)
class PdfParserConfig:
    character_density_threshold: int = 50
    timeout_seconds: float = 60.0
    ocr_timeout_seconds: float = 10.0
    ocr: OCRFunction | None = None
    limits: PdfParserLimits = PdfParserLimits()

    def __post_init__(self) -> None:
        if self.character_density_threshold < 0:
            raise ValueError("character_density_threshold must not be negative")
        if self.timeout_seconds <= 0 or self.ocr_timeout_seconds <= 0:
            raise ValueError("timeouts must be positive")


class PdfParser:
    """Parse ordinary and scanned PDFs without remote services."""

    def __init__(self, config: PdfParserConfig | None = None) -> None:
        self.config = config or PdfParserConfig()

    @staticmethod
    def detect_format(raw: RawDocument) -> DocumentFormat:
        if raw.raw_content.startswith(b"%PDF-"):
            return DocumentFormat.PDF
        raise ParseError("content is not a PDF")

    def parse(self, raw: RawDocument) -> ParsedDocument:
        self._validate_input(raw)
        return run_document(self, raw, self.config.timeout_seconds)

    def _validate_input(self, raw: RawDocument) -> None:
        if len(raw.raw_content) > self.config.limits.max_bytes:
            raise ParseError("PDF byte limit exceeded")
        self.detect_format(raw)

    def _parse_document(self, raw: RawDocument) -> ParsedDocument:
        started = time.monotonic()
        try:
            document = pdfium.PdfDocument(raw.raw_content)
            page_count = len(document)
            self._check_page_count(page_count)
            pages, blocks, warnings = self._extract(document, raw.raw_content, page_count, started)
        except ParseError:
            raise
        except (pdfium.PdfiumError, OSError, ValueError, RuntimeError) as exc:
            raise ParseError(f"PDF parsing failed: {exc}") from exc
        return ParsedDocument(
            raw.doc_id,
            datetime.now(UTC),
            DocumentFormat.PDF,
            tuple(blocks),
            tuple(pages),
            raw.metadata,
            tuple(warnings),
        )

    def _check_page_count(self, page_count: int) -> None:
        if page_count > self.config.limits.max_pages:
            raise ParseError("PDF page limit exceeded")

    def _extract(
        self,
        document: pdfium.PdfDocument,
        content: bytes,
        page_count: int,
        started: float,
    ) -> tuple[list[ParsedPage], list[ParsedBlock], list[ParseWarning]]:
        pages: list[ParsedPage] = []
        blocks: list[ParsedBlock] = []
        warnings: list[ParseWarning] = []
        with pdfplumber.open(BytesIO(content)) as plumber:
            for index in range(page_count):
                self._check_timeout(started)
                page_num = index + 1
                text = self._page_text(document, index)
                scanned = len(text.strip()) < self.config.character_density_threshold
                page_warnings: list[ParseWarning] = []
                if scanned:
                    text, page_warnings = self._ocr_page(document, index, page_num, started)
                tables = self._tables(plumber.pages[index])
                pages.append(ParsedPage(page_num, text, scanned, tables, tuple(page_warnings)))
                warnings.extend(page_warnings)
                if text.strip():
                    blocks.append(
                        ParsedBlock(
                            f"page-{page_num}",
                            BlockType.PARAGRAPH,
                            text.strip(),
                            page_num,
                            (1, max(1, len(text.splitlines()))),
                            None,
                        )
                    )
                blocks.extend(
                    ParsedBlock(
                        f"page-{page_num}-table-{table_index + 1}",
                        BlockType.TABLE,
                        _table_text(table),
                        page_num,
                        None,
                        None,
                    )
                    for table_index, table in enumerate(tables)
                )
        return pages, blocks, warnings

    @staticmethod
    def _page_text(document: pdfium.PdfDocument, index: int) -> str:
        page = document[index]
        text_page = page.get_textpage()
        return str(text_page.get_text_range())

    def _ocr_page(
        self, document: pdfium.PdfDocument, index: int, page_num: int, started: float
    ) -> tuple[str, list[ParseWarning]]:
        if self.config.ocr is None:
            return "", [
                ParseWarning(page_num, "OCR unavailable: no OCR function configured", "error")
            ]
        page = document[index]
        width, height = page.get_size()
        dpi = self.config.limits.max_dpi
        expected_width = math.ceil(width * dpi / 72)
        expected_height = math.ceil(height * dpi / 72)
        if not self._dimensions_allowed(expected_width, expected_height):
            return "", [
                ParseWarning(page_num, "OCR page dimensions exceed configured limits", "error")
            ]
        remaining = self._remaining_seconds(started)
        if remaining <= 0:
            raise ParseError("PDF parsing timed out")
        image, actual_size = render_page_with_size(page, dpi)
        actual_width, actual_height = actual_size
        if not self._dimensions_allowed(actual_width, actual_height):
            return "", [
                ParseWarning(page_num, "OCR rendered dimensions exceed configured limits", "error")
            ]
        if len(image) > self.config.limits.max_ocr_bytes:
            return "", [ParseWarning(page_num, "OCR image byte limit exceeded", "error")]
        return run_ocr(
            self.config.ocr,
            image,
            page_num,
            min(self.config.ocr_timeout_seconds, remaining),
            inherit_session=True,
        )

    def _dimensions_allowed(self, width: int, height: int) -> bool:
        limits = self.config.limits
        return (
            width * height <= limits.max_page_pixels and max(width, height) <= limits.max_dimension
        )

    @staticmethod
    def _tables(page: pdfplumber.page.Page) -> tuple[ParsedTable, ...]:
        extracted = page.extract_tables() or []
        return tuple(
            ParsedTable(tuple(tuple(cell or "" for cell in row) for row in table))
            for table in extracted
        )

    def _check_timeout(self, started: float) -> None:
        if self._remaining_seconds(started) <= 0:
            raise ParseError("PDF parsing timed out")

    def _remaining_seconds(self, started: float) -> float:
        return self.config.timeout_seconds - (time.monotonic() - started)


def _table_text(table: ParsedTable) -> str:
    return "\n".join(" | ".join(row) for row in table.rows)


__all__ = ["PdfParser", "PdfParserConfig", "PdfParserLimits"]
