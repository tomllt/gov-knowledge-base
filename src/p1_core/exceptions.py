"""P1 核心库结构化异常体系。

所有领域异常必须继承 `P1CoreError`，禁止捕获后静默吞掉或转译为裸 `Exception`。
"""

from __future__ import annotations


class P1CoreError(Exception):
    """P1 核心库基础异常。

    所有由本包抛出的可预期错误都应继承该类型，便于上层统一捕获与日志追踪。
    """


class ValidationError(P1CoreError):
    """数据校验失败。

    适用于必填字段缺失、字段值越界、引用一致性破坏等可静态校验的错误。
    """


class SerializationError(P1CoreError):
    """序列化或反序列化失败。

    适用于数据字典字段类型不符、缺失关键键、JSON/二进制编码异常等情况。
    """


class IngestError(P1CoreError):
    """采集阶段失败。

    数据源连接失败、文件读取失败、格式解码失败等采集期问题归入此异常。
    """


class ParseError(P1CoreError):
    """解析阶段失败。

    PDF/Word/HTML 解析器自身异常、超时、扫描件 OCR 失败等问题归入此异常。
    """


class ChunkError(P1CoreError):
    """切分阶段失败。

    切分器配置错误、块结构不可恢复、切分循环溢出等问题归入此异常。
    """
