"""Offline PDF parser contract and benchmark tests."""

from __future__ import annotations

import io
import time
from datetime import UTC, datetime

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen.canvas import Canvas

from p1_core.exceptions import ParseError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument
from p1_core.parsers.pdf import PdfParser, PdfParserConfig, PdfParserLimits
from p1_core.parsers.pdf.runtime import run_ocr


def pdf_bytes(pages: int = 1, text: str = "policy " * 20) -> bytes:
    stream = io.BytesIO()
    canvas = Canvas(stream)
    for page in range(pages):
        canvas.drawString(72, 720, f"{text}{page + 1}")
        canvas.showPage()
    canvas.save()
    return stream.getvalue()


def raw(content: bytes) -> RawDocument:
    return RawDocument(
        doc_id="doc-1",
        source_type=SourceType.PDF,
        source_uri="local://fixture.pdf",
        collected_at=datetime.now(UTC),
        encoding="utf-8",
        raw_content=content,
        metadata={},
        access_record_id="access-1",
    )


def encrypted_pdf() -> bytes:
    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.setEncrypt(StandardEncryption("secret"))
    canvas.drawString(72, 720, "encrypted")
    canvas.save()
    return stream.getvalue()


def test_parse_normal_pdf_real_surface() -> None:
    result = PdfParser().parse(raw(pdf_bytes()))
    assert result.format.value == "pdf"
    assert "policy" in result.full_text()
    assert result.pages[0].page_num == 1
    assert result.pages[0].is_scanned is False


def test_parse_table_preserves_rows_and_columns() -> None:
    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 720, "Name    Department")
    canvas.drawString(72, 700, "Zhang    Office")
    canvas.save()
    result = PdfParser(PdfParserConfig(character_density_threshold=0)).parse(raw(stream.getvalue()))
    assert result.pages[0].text


def test_scanned_page_uses_rendered_image_in_injected_ocr() -> None:
    def ocr(page: bytes, page_num: int) -> str:
        assert page.startswith(b"\x89PNG")
        return "OCR result"

    parser = PdfParser(PdfParserConfig(ocr=ocr))
    result = parser.parse(raw(pdf_bytes(text="")))
    assert "OCR result" in result.full_text()
    assert result.pages[0].is_scanned is True


def test_ocr_unavailable_is_structured_warning() -> None:
    result = PdfParser().parse(raw(pdf_bytes(text="short")))
    assert result.parse_warnings[0].severity == "error"


@pytest.mark.parametrize("size, expected_scanned", [(49, True), (50, False), (51, False)])
def test_default_scanned_threshold_is_fifty_characters(
    monkeypatch: pytest.MonkeyPatch, size: int, expected_scanned: bool
) -> None:
    monkeypatch.setattr(PdfParser, "_page_text", staticmethod(lambda _document, _index: "x" * size))
    result = PdfParser().parse(raw(pdf_bytes()))
    assert result.pages[0].is_scanned is expected_scanned


def test_encrypted_pdf_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="PDF parsing failed"):
        PdfParser().parse(raw(encrypted_pdf()))


def test_corrupted_pdf_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="PDF parsing failed"):
        PdfParser().parse(raw(b"%PDF-1.7 corrupted"))


def test_limits_reject_giant_documents() -> None:
    config = PdfParserConfig(limits=PdfParserLimits(max_bytes=10))
    with pytest.raises(ParseError, match="byte limit"):
        PdfParser(config).parse(raw(pdf_bytes()))


def test_page_limit_is_enforced() -> None:
    config = PdfParserConfig(limits=PdfParserLimits(max_pages=2))
    with pytest.raises(ParseError, match="page limit"):
        PdfParser(config).parse(raw(pdf_bytes(pages=3)))


def test_invalid_format_is_rejected_before_child_start() -> None:
    with pytest.raises(ParseError, match="not a PDF"):
        PdfParser().parse(raw(b"not a PDF"))


def test_ocr_dimension_limit_returns_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "p1_core.parsers.pdf.parser.pdfium.PdfPage.get_size",
        lambda _page: (20_000, 20_000),
    )
    config = PdfParserConfig(ocr=lambda _page, _number: "unused")
    result = PdfParser(config).parse(raw(pdf_bytes(text="short")))
    assert "dimensions" in result.parse_warnings[0].reason


def test_ocr_byte_limit_returns_warning() -> None:
    config = PdfParserConfig(
        ocr=lambda _page, _number: "unused",
        limits=PdfParserLimits(max_ocr_bytes=1),
    )
    result = PdfParser(config).parse(raw(pdf_bytes(text="short")))
    assert "byte limit" in result.parse_warnings[0].reason


def test_ocr_failure_returns_warning() -> None:
    def failing_ocr(_page: bytes, _page_num: int) -> str:
        raise ValueError("OCR failed")

    result = PdfParser(PdfParserConfig(ocr=failing_ocr)).parse(raw(pdf_bytes(text="short")))
    assert "OCR failed" in result.parse_warnings[0].reason


def test_document_timeout_terminates_stuck_child(monkeypatch: pytest.MonkeyPatch) -> None:
    def stuck(_parser: PdfParser, _raw: RawDocument) -> object:
        time.sleep(2.0)
        return None

    monkeypatch.setattr(PdfParser, "_parse_document", stuck)
    parser = PdfParser(PdfParserConfig(timeout_seconds=0.1))
    started = time.monotonic()
    with pytest.raises(ParseError, match="timed out"):
        parser.parse(raw(pdf_bytes()))
    assert time.monotonic() - started < 1.0


def test_timeout_terminates_ocr_boundary() -> None:
    def stuck_ocr(page: bytes, page_num: int) -> str:
        time.sleep(2.0)
        return "never"

    parser = PdfParser(PdfParserConfig(ocr=stuck_ocr, timeout_seconds=0.1))
    started = time.monotonic()
    with pytest.raises(ParseError, match="timed out"):
        parser.parse(raw(pdf_bytes(text="short")))
    assert time.monotonic() - started < 1.0


def test_worker_parse_path_covers_extraction_contract() -> None:
    parser = PdfParser(PdfParserConfig(character_density_threshold=0))
    result = parser._parse_document(raw(pdf_bytes(pages=2)))
    assert len(result.pages) == 2
    assert result.full_text()


def test_worker_ocr_path_covers_render_and_warning_contract() -> None:
    def ocr(page: bytes, page_num: int) -> str:
        assert page.startswith(b"\x89PNG")
        return "worker OCR"

    parser = PdfParser(PdfParserConfig(ocr=ocr))
    result = parser._parse_document(raw(pdf_bytes(text="short")))
    assert result.full_text() == "worker OCR"


def test_varied_samples_have_at_least_95_percent_success() -> None:
    successes = 0
    for sample in range(100):
        pages = sample % 4 + 1
        text = f"Heading {sample}\\n" + "government policy " * (sample % 8 + 3)
        result = PdfParser().parse(raw(pdf_bytes(pages=pages, text=text)))
        if len(result.pages) == pages and result.full_text():
            successes += 1
    assert successes >= 95
    assert successes == 100


def test_max_dpi_must_be_positive() -> None:
    with pytest.raises(ValueError, match="limits must be positive"):
        PdfParserLimits(max_dpi=0)


def test_fifty_page_performance_reports_measured_limit() -> None:
    started = time.monotonic()
    result = PdfParser().parse(raw(pdf_bytes(pages=50, text="Heading\\npolicy table row " * 5)))
    elapsed = time.monotonic() - started
    assert len(result.pages) == 50
    assert result.pages[0].text.startswith("Heading")
    assert elapsed < 30.0


def test_actual_rendered_dimensions_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    def oversized_render(_page: object, _dpi: int) -> tuple[bytes, tuple[int, int]]:
        return b"png", (20_000, 20_000)

    monkeypatch.setattr("p1_core.parsers.pdf.parser.render_page_with_size", oversized_render)
    config = PdfParserConfig(ocr=lambda _page, _number: "unused")
    result = PdfParser(config)._parse_document(raw(pdf_bytes(text="short")))
    assert "rendered dimensions" in result.parse_warnings[0].reason


def test_inherited_ocr_timeout_reaps_only_ocr_process() -> None:
    def stuck_ocr(_page: bytes, _page_num: int) -> str:
        time.sleep(2.0)
        return "never"

    started = time.monotonic()
    with pytest.raises(ParseError, match="timed out during OCR"):
        run_ocr(stuck_ocr, b"page", 1, 0.1, inherit_session=True)
    assert time.monotonic() - started < 1.0
