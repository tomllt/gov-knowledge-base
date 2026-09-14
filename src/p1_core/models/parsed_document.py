"""Parsed document domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models._validators import (
    require_aware_datetime,
    require_line_range,
    require_nonempty_str,
    require_positive_page,
)
from p1_core.models.enums import BlockType, DocumentFormat
from p1_core.models.heading import HeadingPath

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ParseWarning:
    page_num: int
    reason: str
    severity: Literal["warning", "error"]

    def __post_init__(self) -> None:
        require_positive_page(self.page_num, field="page_num")
        require_nonempty_str(self.reason, field="reason")

    def to_dict(self) -> JsonObject:
        return {"page_num": self.page_num, "reason": self.reason, "severity": self.severity}


@dataclass(frozen=True, slots=True)
class ParsedTable:
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_num: int
    text: str
    is_scanned: bool = False
    tables: tuple[ParsedTable, ...] = ()
    warnings: tuple[ParseWarning, ...] = ()

    def __post_init__(self) -> None:
        require_positive_page(self.page_num, field="page_num")
        if not isinstance(self.text, str):
            raise ValidationError("text must be str")

    def to_dict(self) -> JsonObject:
        return {
            "page_num": self.page_num,
            "text": self.text,
            "is_scanned": self.is_scanned,
            "tables": [{"rows": [list(row) for row in table.rows]} for table in self.tables],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, JsonValue]) -> ParsedPage:
        tables_raw = data.get("tables", [])
        warnings_raw = data.get("warnings", [])
        if not isinstance(tables_raw, list) or not isinstance(warnings_raw, list):
            raise SerializationError("invalid page collections")
        page_num = _required_int(data, "page_num")
        text = _required_str(data, "text")
        tables = tuple(_table_from_dict(item) for item in tables_raw)
        warnings = tuple(_warning_from_dict(item) for item in warnings_raw)
        is_scanned = data.get("is_scanned", False)
        if not isinstance(is_scanned, bool):
            raise SerializationError("is_scanned must be bool")
        return cls(page_num, text, is_scanned, tables, warnings)


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    block_id: str
    block_type: BlockType
    text: str
    page: int | None
    line_range: tuple[int, int] | None
    heading_path: HeadingPath | None

    def __post_init__(self) -> None:
        require_nonempty_str(self.block_id, field="block_id")
        if not isinstance(self.text, str):
            raise ValidationError("text must be str")
        require_positive_page(self.page, field="page")
        require_line_range(self.line_range, field="line_range")


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    raw_doc_id: str
    parsed_at: datetime
    format: DocumentFormat
    blocks: tuple[ParsedBlock, ...]
    pages: tuple[ParsedPage, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    parse_warnings: tuple[ParseWarning, ...] = ()

    def __post_init__(self) -> None:
        require_nonempty_str(self.raw_doc_id, field="raw_doc_id")
        require_aware_datetime(self.parsed_at, field="parsed_at")
        if not isinstance(self.blocks, tuple):
            raise ValidationError("blocks must be tuple[ParsedBlock, ...]")
        for index, block in enumerate(self.blocks):
            if not isinstance(block, ParsedBlock):
                raise ValidationError(f"blocks[{index}] must be ParsedBlock")
        if not isinstance(self.pages, tuple) or not all(
            isinstance(page, ParsedPage) for page in self.pages
        ):
            raise ValidationError("pages must be tuple[ParsedPage, ...]")
        if not isinstance(self.parse_warnings, tuple) or not all(
            isinstance(warning, ParseWarning) for warning in self.parse_warnings
        ):
            raise ValidationError("parse_warnings must be tuple[ParseWarning, ...]")

    def full_text(self, sep: str = "\n\n") -> str:
        return sep.join(block.text for block in self.blocks)

    def to_dict(self) -> JsonObject:
        return {
            "raw_doc_id": self.raw_doc_id,
            "parsed_at": self.parsed_at.isoformat(),
            "format": self.format.value,
            "blocks": [_block_dict(block) for block in self.blocks],
            "pages": [page.to_dict() for page in self.pages],
            "metadata": dict(self.metadata),
            "parse_warnings": [warning.to_dict() for warning in self.parse_warnings],
        }

    def __hash__(self) -> int:
        return hash((self.raw_doc_id, self.parsed_at, self.format, self.blocks))

    @classmethod
    def from_dict(cls, data: Mapping[str, JsonValue]) -> ParsedDocument:
        try:
            blocks_raw = data["blocks"]
            if not isinstance(blocks_raw, list):
                raise SerializationError("ParsedDocument.blocks must be Sequence")
            pages_raw = data.get("pages", [])
            warnings_raw = data.get("parse_warnings", [])
            metadata_raw = data.get("metadata", {})
            if not isinstance(pages_raw, list) or not isinstance(warnings_raw, list):
                raise SerializationError("invalid document collections")
            metadata = _metadata_from_json(metadata_raw)
            return cls(
                _required_str(data, "raw_doc_id"),
                _parse_datetime(data),
                _parse_format(data),
                tuple(_parse_block(item) for item in blocks_raw),
                tuple(ParsedPage.from_dict(_required_mapping(item, "page")) for item in pages_raw),
                metadata,
                tuple(
                    _warning_from_dict(_required_mapping(item, "parse warning"))
                    for item in warnings_raw
                ),
            )
        except KeyError as exc:
            raise SerializationError(f"ParsedDocument missing key: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise SerializationError(f"ParsedDocument deserialization failed: {exc}") from exc


def _block_dict(block: ParsedBlock) -> JsonObject:
    heading_path: JsonValue = None
    if block.heading_path is not None:
        heading_path = {"parts": list(block.heading_path.parts)}
    return {
        "block_id": block.block_id,
        "block_type": block.block_type.value,
        "text": block.text,
        "page": block.page,
        "line_range": list(block.line_range) if block.line_range else None,
        "heading_path": heading_path,
    }


def _metadata_from_json(value: JsonValue) -> Mapping[str, str]:
    if not isinstance(value, dict):
        raise SerializationError("metadata must be object[str, str]")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str):
            raise SerializationError("metadata must be object[str, str]")
        result[key] = item
    return result


def _required_str(data: Mapping[str, JsonValue], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise SerializationError(f"{key} must be str")
    return value


def _required_int(data: Mapping[str, JsonValue], key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise SerializationError(f"{key} must be int")
    return value


def _parse_datetime(data: Mapping[str, JsonValue]) -> datetime:
    return datetime.fromisoformat(_required_str(data, "parsed_at"))


def _parse_format(data: Mapping[str, JsonValue]) -> DocumentFormat:
    return DocumentFormat(_required_str(data, "format"))


def _required_mapping(value: JsonValue, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise SerializationError(f"{field} must be Mapping")
    return value


def _table_from_dict(item: JsonValue) -> ParsedTable:
    if not isinstance(item, dict):
        raise SerializationError("invalid table")
    rows = item.get("rows")
    if not isinstance(rows, list):
        raise SerializationError("invalid table rows")
    parsed_rows: list[tuple[str, ...]] = []
    for row in rows:
        if not isinstance(row, list) or not all(isinstance(cell, str) for cell in row):
            raise SerializationError("table cells must be str")
        parsed_rows.append(tuple(cell for cell in row if isinstance(cell, str)))
    return ParsedTable(tuple(parsed_rows))


def _warning_from_dict(item: JsonValue) -> ParseWarning:
    if not isinstance(item, dict):
        raise SerializationError("invalid parse warning")
    page_num = item.get("page_num")
    reason = item.get("reason")
    severity = item.get("severity")
    if not isinstance(page_num, int) or isinstance(page_num, bool):
        raise SerializationError("invalid parse warning")
    if not isinstance(reason, str):
        raise SerializationError("invalid parse warning")
    if severity == "warning":
        return ParseWarning(page_num, reason, "warning")
    if severity == "error":
        return ParseWarning(page_num, reason, "error")
    raise SerializationError("invalid parse warning")


def _parse_block(item: JsonValue) -> ParsedBlock:
    if not isinstance(item, dict):
        raise SerializationError("ParsedDocument.blocks[*] must be Mapping")
    page = item.get("page")
    if page is not None and (not isinstance(page, int) or isinstance(page, bool)):
        raise SerializationError("block.page must be int or None")
    line = item.get("line_range")
    line_range: tuple[int, int] | None = None
    if line is not None:
        if not isinstance(line, list) or len(line) != 2:
            raise SerializationError("block.line_range must be (int, int) or None")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in line):
            raise SerializationError("block.line_range entries must be int")
        start = line[0]
        end = line[1]
        if not isinstance(start, int) or not isinstance(end, int):
            raise SerializationError("block.line_range entries must be int")
        line_range = (start, end)
    heading = item.get("heading_path")
    if heading is not None and not isinstance(heading, dict):
        raise SerializationError("block.heading_path must be Mapping or None")
    return ParsedBlock(
        _required_str(item, "block_id"),
        BlockType(_required_str(item, "block_type")),
        _required_str(item, "text"),
        page,
        line_range,
        HeadingPath.from_dict(heading) if isinstance(heading, dict) else None,
    )


__all__ = [
    "JsonObject",
    "JsonValue",
    "ParseWarning",
    "ParsedBlock",
    "ParsedDocument",
    "ParsedPage",
    "ParsedTable",
]
