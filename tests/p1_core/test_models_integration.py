"""模型层公开 API 整合测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from p1_core.models import (
    BlockType,
    ChunkQuality,
    DocumentFormat,
    HeadingPath,
    KnowledgeChunk,
    ParsedBlock,
    ParsedDocument,
    RawDocument,
    SourceType,
    utcnow,
)


def test_all_public_symbols_exported() -> None:
    """确保 `p1_core.models` 公开 API 稳定。"""
    assert HeadingPath is not None
    assert RawDocument is not None
    assert ParsedDocument is not None
    assert ParsedBlock is not None
    assert KnowledgeChunk is not None
    assert SourceType.PDF.value == "pdf"
    assert DocumentFormat.PDF.value == "pdf"
    assert BlockType.PARAGRAPH.value == "paragraph"
    assert ChunkQuality.OK.value == "ok"
    assert utcnow().tzinfo is not None


def test_pipeline_can_chain_through_stages() -> None:
    """集成：RawDocument → ParsedDocument → KnowledgeChunk 完整链路。"""
    raw = RawDocument(
        doc_id="01HV3A1B2C3D4E5F6G7H8J9K0L",
        source_type=SourceType.PDF,
        source_uri="s3://bucket/123.pdf",
        collected_at=utcnow(),
        encoding="utf-8",
        raw_content=b"%PDF-1.4 mock",
        metadata={"department": "公安局"},
        access_record_id="AR-2026-0001",
    )
    block = ParsedBlock(
        block_id="blk-001",
        block_type=BlockType.HEADING,
        text="第 1 章 总则",
        page=1,
        line_range=(1, 1),
        heading_path=HeadingPath.root("第 1 章 总则"),
    )
    parsed = ParsedDocument(
        raw_doc_id=raw.doc_id,
        parsed_at=utcnow(),
        format=DocumentFormat.PDF,
        blocks=(block,),
    )
    chunk = KnowledgeChunk(
        chunk_id="ch-001",
        raw_doc_id=raw.doc_id,
        parsed_doc_id=parsed.raw_doc_id + ":p",
        heading_path=block.heading_path or HeadingPath.root(""),
        text=block.text,
        page=block.page,
        line_range=block.line_range,
        parent_chunk_id=None,
        quality_flag=ChunkQuality.OK,
    )

    # 完整链路必须保持 raw_doc_id 一致
    assert chunk.raw_doc_id == raw.doc_id == parsed.raw_doc_id
    # parsed_at 应该是 tz-aware
    assert isinstance(parsed.parsed_at, datetime)
    assert parsed.parsed_at.tzinfo == UTC
    # full_text 输出与块文本一致
    assert parsed.full_text() == block.text
