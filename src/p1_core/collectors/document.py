"""Word 文件采集器。

将 ``.doc``/``.docx`` 文件转换为 ``RawDocument``:

  - ``.docx`` (OOXML, zip 包): 使用 :mod:`python_docx` 读取段落与表格的结构
    统计, 写入 ``RawDocument.metadata``; 原始字节流原样保留供下游解析器消费。
  - ``.doc`` (旧二进制 OLE2 复合文档): 当前阶段不解析 (解析逻辑保留给
    F02 阶段), 抛出 :class:`UnsupportedFormatError` 供审计层标记
    ``unsupported_format``.

与 PDF / API 等采集器共享 :class:`p1_core.collectors.base.BaseCollector` 抽象,
故接入记录 / 审计日志 / 脱敏中间件 / 隔离区等横切关注点由编排器统一注入。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from docx import Document as DocxDocument
from docx.opc.exceptions import OpcError, PackageNotFoundError
from docx.table import Table

from p1_core.collectors.base import BaseCollector, UnsupportedFormatError
from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument
from p1_core.models.time_utils import utcnow

_OOXML_NS_RE = re.compile(
    r"wordprocessingml/(\d{4})/main|word/(\d{4})/wordml|officeDocument/(\d{4})/extended",
)


class WordFileCollector(BaseCollector):
    """Word 文件采集器 (``docx`` 主路径, ``doc`` 标记 unsupported_format)。"""

    source_type: ClassVar[SourceType] = SourceType.WORD
    _SUPPORTED_EXTENSIONS: ClassVar[frozenset[str]] = frozenset({".docx", ".doc"})

    def supported_extensions(self) -> frozenset[str]:
        return self._SUPPORTED_EXTENSIONS

    def collect(self, path: Path) -> RawDocument:
        if not path.exists():
            msg = f"word file not found: {path}"
            raise IngestError(msg)
        suffix = path.suffix.lower()
        if suffix == ".doc":
            msg = f"unsupported_format: legacy .doc is not supported ({path})"
            raise UnsupportedFormatError(msg)
        if suffix != ".docx":
            msg = (
                f"unsupported_format: extension {suffix!r} "
                f"not in {sorted(self._SUPPORTED_EXTENSIONS)}"
            )
            raise UnsupportedFormatError(msg)
        raw = path.read_bytes()
        return self._collect_docx(path, raw)

    @staticmethod
    def _collect_docx(path: Path, raw: bytes) -> RawDocument:
        if not raw:
            msg = f"empty docx file: {path}"
            raise IngestError(msg)
        try:
            document = DocxDocument(BytesIO(raw))
        except (
            zipfile.BadZipFile,
            PackageNotFoundError,
            OpcError,
            KeyError,
            AttributeError,
            IndexError,
            ValueError,
        ) as exc:
            # encrypted / truncated / malformed 都归类为 IngestError,
            # 由编排层决定是否进入隔离区。
            msg = f"invalid or encrypted docx ({path}): {exc}"
            raise IngestError(msg) from exc

        metadata = MappingProxyType(
            {
                "ooxml_version": _detect_ooxml_version(raw),
                "paragraph_count": str(len(document.paragraphs)),
                "table_count": str(len(document.tables)),
                "table_row_count": str(_max_row_count(document.tables)),
                "table_column_count": str(_max_column_count(document.tables)),
                "core_version": document.core_properties.version or "",
            }
        )

        doc_id = _stable_doc_id(raw)
        return RawDocument(
            doc_id=doc_id,
            source_type=SourceType.WORD,
            source_uri=str(path),
            collected_at=utcnow(),
            encoding="utf-8",
            raw_content=raw,
            metadata=metadata,
            access_record_id=f"AR-{doc_id}",
        )


def _detect_ooxml_version(raw: bytes) -> str:
    """从 docx 包内的命名空间推断 OOXML 版本年份, 例如 ``2006`` / ``2013``.

    解析失败时回退到 ``"unknown"`` , 避免阻塞采集主流程。
    """
    try:
        with zipfile.ZipFile(BytesIO(raw)) as zf:
            for member in ("word/document.xml", "[Content_Types].xml", "docProps/app.xml"):
                try:
                    payload = zf.read(member).decode("utf-8", errors="replace")
                except KeyError:
                    continue
                match = _OOXML_NS_RE.search(payload)
                if match:
                    year = next(group for group in match.groups() if group)
                    return f"OOXML/{year}"
    except zipfile.BadZipFile:
        return "unknown"
    return "unknown"


def _stable_doc_id(raw: bytes) -> str:
    """基于内容生成稳定的 16-hex 字符 doc_id, 跨运行可复现。"""
    return hashlib.sha256(raw).hexdigest()[:16]


def _max_row_count(tables: list[Table]) -> int:
    rows = 0
    for table in tables:
        rows = max(rows, len(table.rows))
    return rows


def _max_column_count(tables: list[Table]) -> int:
    cols = 0
    for table in tables:
        cols = max(cols, len(table.columns))
    return cols


__all__ = ["WordFileCollector"]


def _run_cli() -> int:
    """命令行入口: ``python -m p1_core.collectors.document --input <dir>``.

    打印每份文件的采集状态 (成功 / unsupported_format / 其它错误), 最后汇总。
    返回 exit code: 0 = 全部成功, 1 = 出现 IngestError (供 CI 串联)。
    """
    parser = argparse.ArgumentParser(
        prog="p1_core.collectors.document",
        description="Word file collector (.doc/.docx).",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="待采集的目录路径。",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="递归扫描子目录。",
    )
    args = parser.parse_args()

    collector = WordFileCollector()
    success = 0
    errored = 0
    for result in collector.iter_directory(args.input, recursive=args.recursive):
        if isinstance(result, UnsupportedFormatError):
            print(f"UNSUPPORTED_FORMAT\t{result}", file=sys.stderr)
            errored += 1
        elif isinstance(result, Exception):
            print(f"ERROR\t{result}", file=sys.stderr)
            errored += 1
        else:
            print(f"OK\t{result.source_uri}\t{result.doc_id}")
            success += 1
    print(f"# summary: success={success} errored={errored}", file=sys.stderr)
    return 0 if errored == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run_cli())
