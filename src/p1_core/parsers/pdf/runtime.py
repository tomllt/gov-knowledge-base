"""Process boundaries for PDF parsing and OCR."""

from __future__ import annotations

import multiprocessing
import os
import signal
from contextlib import suppress
from dataclasses import dataclass
from io import BytesIO
from multiprocessing.process import BaseProcess
from queue import Empty
from typing import Protocol

import pypdfium2 as pdfium
from PIL import Image

from p1_core.exceptions import ParseError
from p1_core.models.parsed_document import ParsedDocument, ParseWarning
from p1_core.models.raw_document import RawDocument


class OCRFunction(Protocol):
    def __call__(self, page: bytes, page_num: int) -> str: ...


class ParserWorker(Protocol):
    def _parse_document(self, raw: RawDocument) -> ParsedDocument: ...


@dataclass(frozen=True, slots=True)
class ParseResult:
    document: ParsedDocument | None
    error: str | None


def run_document(parser: ParserWorker, raw: RawDocument, timeout: float) -> ParsedDocument:
    context = multiprocessing.get_context("fork")
    queue: multiprocessing.Queue[ParseResult] = context.Queue()
    process = context.Process(target=_document_worker, args=(parser, raw, queue))
    process.start()
    try:
        process.join(timeout)
        if process.is_alive():
            _terminate_process_group(process, process_group_id=process.pid)
            raise ParseError("PDF parsing timed out")
        try:
            result = queue.get(timeout=0.1)
        except Empty as exc:
            raise ParseError("PDF parsing failed without a result") from exc
    finally:
        queue.close()
        queue.join_thread()
    if result.error is not None:
        raise ParseError(result.error)
    if result.document is None:
        raise ParseError("PDF parsing failed without a result")
    return result.document


def _document_worker(
    parser: ParserWorker, raw: RawDocument, queue: multiprocessing.Queue[ParseResult]
) -> None:
    os.setsid()
    try:
        queue.put(ParseResult(parser._parse_document(raw), None))
    except ParseError as exc:
        queue.put(ParseResult(None, str(exc)))
    except (pdfium.PdfiumError, OSError, ValueError, RuntimeError) as exc:
        queue.put(ParseResult(None, f"PDF parsing failed: {exc}"))


def render_page_with_size(page: pdfium.PdfPage, dpi: int) -> tuple[bytes, tuple[int, int]]:
    bitmap = page.render(scale=dpi / 72)
    try:
        image: Image.Image = bitmap.to_pil()
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue(), image.size
    finally:
        bitmap.close()


def render_page(page: pdfium.PdfPage, dpi: int) -> bytes:
    content, _size = render_page_with_size(page, dpi)
    return content


def run_ocr(
    ocr: OCRFunction,
    content: bytes,
    page_num: int,
    timeout: float,
    *,
    inherit_session: bool = False,
) -> tuple[str, list[ParseWarning]]:
    context = multiprocessing.get_context("fork")
    queue: multiprocessing.Queue[str] = context.Queue()
    process = context.Process(
        target=_ocr_worker, args=(ocr, content, page_num, queue, inherit_session)
    )
    process.start()
    try:
        process.join(timeout)
        if process.is_alive():
            _terminate_process_group(
                process, process_group_id=None if inherit_session else process.pid
            )
            raise ParseError("PDF parsing timed out during OCR")
        try:
            result = queue.get(timeout=0.1)
        except Empty:
            return "", [ParseWarning(page_num, "OCR failed without a result", "error")]
    finally:
        queue.close()
        queue.join_thread()
    if result.startswith("__ERROR__:"):
        return "", [ParseWarning(page_num, result[10:], "error")]
    return result, []


def _ocr_worker(
    ocr: OCRFunction,
    content: bytes,
    page_num: int,
    queue: multiprocessing.Queue[str],
    inherit_session: bool,
) -> None:
    if not inherit_session:
        os.setsid()
    try:
        queue.put(ocr(content, page_num))
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        queue.put(f"__ERROR__:{exc}")


def _terminate_process_group(process: BaseProcess, *, process_group_id: int | None = None) -> None:
    """终止进程组或直接 worker，并阻塞回收直接 worker。"""
    if process.pid is None:
        return
    if process_group_id is None:
        process.terminate()
    else:
        with suppress(ProcessLookupError):
            os.killpg(process_group_id, signal.SIGTERM)
    process.join(0.2)
    if process.is_alive():
        if process_group_id is None:
            process.kill()
        else:
            with suppress(ProcessLookupError):
                os.killpg(process_group_id, signal.SIGKILL)
        process.join()
