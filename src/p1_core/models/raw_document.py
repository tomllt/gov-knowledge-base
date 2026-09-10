"""采集阶段产物：`RawDocument`。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from p1_core.exceptions import SerializationError, ValidationError
from p1_core.models._validators import (
    require_aware_datetime,
    require_nonempty_str,
    require_str_dict,
)
from p1_core.models.enums import SourceType

# 规范化编码白名单 —— 采集阶段必须将原始字节流转码为其中之一。
_ALLOWED_ENCODINGS: Final = frozenset({"utf-8", "utf-8-sig", "gb18030", "gbk"})


@dataclass(frozen=True, slots=True)
class RawDocument:
    """采集阶段产物。

    由各类型采集器（PDF/Word/HTML/API/...）产出，已完成：
      - 字符编码标准化（统一为 UTF-8/GB 系列）；
      - 时间字段格式统一；
      - 敏感字段脱敏；
      - 接入记录登记（`access_record_id` 不可为空）。

    Attributes:
        doc_id: 全局唯一文档标识（建议 ULID）。
        source_type: 数据源类型。
        source_uri: 原始数据来源 URI/路径（已脱敏）。
        collected_at: 采集完成时间（必须带时区）。
        encoding: 标准化后的字符编码。
        raw_content: 原始字节流（PDF/Word）或规范化后的文本字节流。
        metadata: 与采集相关的元数据键值对。
        access_record_id: 接入记录 ID（F01 业务规则：接入记录永久保留）。
    """

    doc_id: str
    source_type: SourceType
    source_uri: str
    collected_at: datetime
    encoding: str
    raw_content: bytes
    metadata: Mapping[str, str]
    access_record_id: str

    def __post_init__(self) -> None:
        require_nonempty_str(self.doc_id, field="doc_id")
        require_nonempty_str(self.source_uri, field="source_uri")
        require_aware_datetime(self.collected_at, field="collected_at")
        if self.encoding not in _ALLOWED_ENCODINGS:
            msg = f"encoding must be one of {sorted(_ALLOWED_ENCODINGS)}, got {self.encoding!r}"
            raise ValidationError(msg)
        if not isinstance(self.raw_content, bytes):
            msg = "raw_content must be bytes"
            raise ValidationError(msg)
        # 冻结为不可变映射以保证外部不可篡改；自定义 __hash__ 另行处理哈希问题。
        object.__setattr__(
            self,
            "metadata",
            require_str_dict(self.metadata, field="metadata"),
        )
        require_nonempty_str(self.access_record_id, field="access_record_id")

    def __hash__(self) -> int:
        """稳定哈希：使用业务身份字段；忽略 ``metadata``（人类可读旁路信息）。

        `metadata` 本身用 `MappingProxyType` 包装后哈希不可用，因此手动指定
        仅基于业务字段计算哈希，保证可放入集合/字典。
        """
        return hash(
            (
                self.doc_id,
                self.source_type,
                self.source_uri,
                self.collected_at,
                self.encoding,
                self.raw_content,
                self.access_record_id,
            )
        )

    def to_dict(self) -> dict[str, object]:
        """序列化为可 JSON 化的字典。"""
        return {
            "doc_id": self.doc_id,
            "source_type": self.source_type.value,
            "source_uri": self.source_uri,
            "collected_at": self.collected_at.isoformat(),
            "encoding": self.encoding,
            "raw_content": self.raw_content.hex(),
            "metadata": dict(self.metadata),
            "access_record_id": self.access_record_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RawDocument:
        """从字典反序列化；类型不符时抛出 `SerializationError`。"""
        try:
            doc_id = _expect_str(data, "doc_id")
            source_type_str = _expect_str(data, "source_type")
            source_uri = _expect_str(data, "source_uri")
            collected_at_raw = _expect_str(data, "collected_at")
            encoding = _expect_str(data, "encoding")
            raw_content_hex = _expect_str(data, "raw_content")
            access_record_id = _expect_str(data, "access_record_id")
            metadata_raw = data.get("metadata", {})
            if not isinstance(metadata_raw, Mapping):
                msg = "RawDocument.metadata must be Mapping[str, str]"
                raise SerializationError(msg)
            return cls(
                doc_id=doc_id,
                source_type=SourceType(source_type_str),
                source_uri=source_uri,
                collected_at=datetime.fromisoformat(collected_at_raw),
                encoding=encoding,
                raw_content=bytes.fromhex(raw_content_hex),
                metadata=dict(metadata_raw),
                access_record_id=access_record_id,
            )
        except KeyError as exc:
            msg = f"RawDocument missing key: {exc.args[0]}"
            raise SerializationError(msg) from exc
        except (TypeError, ValueError) as exc:
            msg = f"RawDocument deserialization failed: {exc}"
            raise SerializationError(msg) from exc


def _expect_str(data: Mapping[str, object], key: str) -> str:
    """从映射中取出指定键并要求为 `str`；缺失或类型不符抛 `SerializationError`。"""
    value = data[key]
    if not isinstance(value, str):
        msg = f"{key} must be str, got {type(value).__name__}"
        raise SerializationError(msg)
    return value


__all__ = ["MappingProxyType", "RawDocument"]
