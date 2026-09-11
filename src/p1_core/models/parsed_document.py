"""解析阶段产物：`ParsedDocument` 与 `ParsedBlock`。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models._validators import (
    require_aware_datetime,
    require_line_range,
    require_nonempty_str,
    require_positive_page,
)
from p1_core.models.enums import BlockType, DocumentFormat
from p1_core.models.heading import HeadingPath


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """解析阶段产出的中间块。

    解析器对原始文档进行一次扫描后得到的最小结构单元，
    用于后续切分阶段按语义层级组块。

    Attributes:
        block_id: 块标识。
        block_type: 块语义类型。
        text: 块文本内容。
        page: 所在页码（无页码概念时为 None）。
        line_range: 起止行号（含），用于回溯定位。
        heading_path: 块所属的标题层级路径。
    """

    block_id: str
    block_type: BlockType
    text: str
    page: int | None
    line_range: tuple[int, int] | None
    heading_path: HeadingPath | None

    def __post_init__(self) -> None:
        require_nonempty_str(self.block_id, field="block_id")
        if not isinstance(self.text, str):
            msg = "text must be str"
            raise ValidationError(msg)
        require_positive_page(self.page, field="page")
        require_line_range(self.line_range, field="line_range")


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """解析阶段产物。

    由解析器（PDF/Word/HTML）对 `RawDocument` 解析得到；`blocks`
    已按文档原始顺序排列，可用于按语义切分或重组为完整文本。

    Attributes:
        raw_doc_id: 关联的 `RawDocument.doc_id`。
        parsed_at: 解析完成时间（必须带时区）。
        format: 解析得到的文档格式。
        blocks: 解析中间块序列。
        render_required: 是否需要浏览器/JS 渲染（如 SPA 骨架页）。
    """

    raw_doc_id: str
    parsed_at: datetime
    format: DocumentFormat
    blocks: tuple[ParsedBlock, ...]
    render_required: bool = False

    def __post_init__(self) -> None:
        require_nonempty_str(self.raw_doc_id, field="raw_doc_id")
        require_aware_datetime(self.parsed_at, field="parsed_at")
        if not isinstance(self.blocks, tuple):
            msg = "blocks must be tuple[ParsedBlock, ...]"
            raise ValidationError(msg)
        for i, blk in enumerate(self.blocks):
            if not isinstance(blk, ParsedBlock):
                msg = f"blocks[{i}] must be ParsedBlock"
                raise ValidationError(msg)

    def full_text(self, sep: str = "\n\n") -> str:
        """将所有块文本按序拼接，返回完整文本。"""
        return sep.join(b.text for b in self.blocks)

    def to_dict(self) -> dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return {
            "raw_doc_id": self.raw_doc_id,
            "parsed_at": self.parsed_at.isoformat(),
            "format": self.format.value,
            "render_required": self.render_required,
            "blocks": [
                {
                    "block_id": b.block_id,
                    "block_type": b.block_type.value,
                    "text": b.text,
                    "page": b.page,
                    "line_range": list(b.line_range) if b.line_range else None,
                    "heading_path": b.heading_path.to_dict() if b.heading_path else None,
                }
                for b in self.blocks
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ParsedDocument:
        """从字典反序列化。"""
        try:
            raw_doc_id = _expect_str(data, "raw_doc_id")
            parsed_at_raw = _expect_str(data, "parsed_at")
            format_raw = _expect_str(data, "format")
            blocks_raw = data["blocks"]
            if not isinstance(blocks_raw, Sequence):
                msg = "ParsedDocument.blocks must be Sequence"
                raise SerializationError(msg)
            blocks: tuple[ParsedBlock, ...] = tuple(_parse_block(item) for item in blocks_raw)
            return cls(
                raw_doc_id=raw_doc_id,
                parsed_at=datetime.fromisoformat(parsed_at_raw),
                format=DocumentFormat(format_raw),
                blocks=blocks,
                render_required=bool(data.get("render_required", False)),
            )
        except KeyError as exc:
            msg = f"ParsedDocument missing key: {exc.args[0]}"
            raise SerializationError(msg) from exc
        except (TypeError, ValueError) as exc:
            msg = f"ParsedDocument deserialization failed: {exc}"
            raise SerializationError(msg) from exc


def _parse_block(item: object) -> ParsedBlock:
    """从单一块字典构造 `ParsedBlock`，类型不符时抛 `SerializationError`。"""
    if not isinstance(item, Mapping):
        msg = "ParsedDocument.blocks[*] must be Mapping"
        raise SerializationError(msg)
    block_id = _expect_str(item, "block_id")
    block_type_raw = _expect_str(item, "block_type")
    text = _expect_str(item, "text")
    page_value = item.get("page")
    page: int | None
    if page_value is None:
        page = None
    elif isinstance(page_value, bool) or not isinstance(page_value, int):
        msg = "block.page must be int or None"
        raise SerializationError(msg)
    else:
        page = page_value
    line_range_value = item.get("line_range")
    line_range: tuple[int, int] | None
    if line_range_value is None:
        line_range = None
    elif (
        not isinstance(line_range_value, Sequence)
        or isinstance(line_range_value, (str, bytes))
        or len(line_range_value) != 2
    ):
        msg = "block.line_range must be (int, int) or None"
        raise SerializationError(msg)
    else:
        start_obj, end_obj = line_range_value
        if (
            isinstance(start_obj, bool)
            or isinstance(end_obj, bool)
            or not isinstance(start_obj, int)
            or not isinstance(end_obj, int)
        ):
            msg = "block.line_range entries must be int"
            raise SerializationError(msg)
        line_range = (start_obj, end_obj)
    heading_path_value = item.get("heading_path")
    heading_path: HeadingPath | None
    if heading_path_value is None:
        heading_path = None
    elif not isinstance(heading_path_value, Mapping):
        msg = "block.heading_path must be Mapping or None"
        raise SerializationError(msg)
    else:
        heading_path = HeadingPath.from_dict(heading_path_value)
    return ParsedBlock(
        block_id=block_id,
        block_type=BlockType(block_type_raw),
        text=text,
        page=page,
        line_range=line_range,
        heading_path=heading_path,
    )


def _expect_str(data: Mapping[str, object], key: str) -> str:
    """从映射中取出指定键并要求为 `str`；缺失或类型不符抛 `SerializationError`。"""
    value = data[key]
    if not isinstance(value, str):
        msg = f"{key} must be str, got {type(value).__name__}"
        raise SerializationError(msg)
    return value


__all__ = ["ParsedBlock", "ParsedDocument"]
