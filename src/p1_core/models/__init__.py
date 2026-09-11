"""P1 核心库公共数据模型。

承载 P1-F01 知识采集接入与 P1-F02 知识解析与切分所共用的领域类型。
所有模型为不可变 `dataclass(slots=True, frozen=True)`，便于在多阶段流水线
之间安全传递并支持哈希/相等性比较。

数据流：

    数据源 ──► RawDocument (采集)
              └──► ParsedDocument (解析)
                    └──► KnowledgeChunk (切分，进入标注)

详细字段含义参见每个子模块的 docstring。
"""

from __future__ import annotations

from p1_core.models.enums import (
    BlockType,
    ChunkQuality,
    DocumentFormat,
    SourceType,
)
from p1_core.models.heading import HeadingPath
from p1_core.models.knowledge_chunk import KnowledgeChunk
from p1_core.models.parsed_document import ParsedBlock, ParsedDocument
from p1_core.models.raw_document import RawDocument
from p1_core.models.time_utils import utcnow

__all__ = [
    "BlockType",
    "ChunkQuality",
    "DocumentFormat",
    "HeadingPath",
    "KnowledgeChunk",
    "ParsedBlock",
    "ParsedDocument",
    "RawDocument",
    "SourceType",
    "utcnow",
]
