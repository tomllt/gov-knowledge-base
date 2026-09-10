"""HTML 文件采集器。

将 ``.html``/``.htm`` 文件转换为 ``RawDocument``：

  - 编码识别按以下优先级：BOM -> ``<meta charset>`` -> chardet 兜底 -> UTF-8 默认；
  - 解析仅做轻量结构嗅探（不解析业务内容，保留给 F02 解析阶段）；
  - 标准化输出为 UTF-8 字节流，写入 ``RawDocument.raw_content``,
    ``RawDocument.metadata`` 记录原始编码与检测来源便于审计追溯。

与 PDF / Word 采集器共享 :class:`p1_core.collectors.base.BaseCollector` 抽象。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

import chardet
from bs4 import BeautifulSoup

from p1_core.collectors.base import BaseCollector, UnsupportedFormatError
from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument
from p1_core.models.time_utils import utcnow

# 仅识别白名单编码：与 ``RawDocument`` 的 ``_ALLOWED_ENCODINGS`` 保持一致。
_ALLOWED_ENCODINGS: frozenset[str] = frozenset({"utf-8", "utf-8-sig", "gb18030", "gbk"})

# 仅扫描首部 N 字节查找 ``<meta charset>``, 避免对大文件做全量正则扫描。
_META_SCAN_BYTES: int = 4096

_META_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?([\w-]+)""",
    re.IGNORECASE,
)


class HtmlFileCollector(BaseCollector):
    """HTML 文件采集器。"""

    source_type: ClassVar[SourceType] = SourceType.HTML
    _SUPPORTED_EXTENSIONS: ClassVar[frozenset[str]] = frozenset({".html", ".htm"})

    def supported_extensions(self) -> frozenset[str]:
        return self._SUPPORTED_EXTENSIONS

    def collect(self, path: Path) -> RawDocument:
        if not path.exists():
            msg = f"html file not found: {path}"
            raise IngestError(msg)
        suffix = path.suffix.lower()
        if suffix not in self._SUPPORTED_EXTENSIONS:
            msg = (
                f"unsupported_format: extension {suffix!r} "
                f"not in {sorted(self._SUPPORTED_EXTENSIONS)}"
            )
            raise UnsupportedFormatError(msg)
        raw = path.read_bytes()
        return self._collect_html(path, raw)

    @staticmethod
    def _collect_html(path: Path, raw: bytes) -> RawDocument:
        text, original_encoding, charset_source = _decode_html(raw)
        # 嗅探：仅统计基本结构信息，不解析正文（解析属于 F02 阶段）。
        soup = BeautifulSoup(text, "html.parser")
        title = ""
        if soup.title is not None and soup.title.string is not None:
            title = soup.title.string.strip()
        metadata = MappingProxyType(
            {
                "original_encoding": original_encoding,
                "charset_source": charset_source,
                "tag_count": str(len(soup.find_all())),
                "title": title,
            }
        )
        normalized = text.encode("utf-8")
        doc_id = _stable_doc_id(normalized)
        return RawDocument(
            doc_id=doc_id,
            source_type=SourceType.HTML,
            source_uri=str(path),
            collected_at=utcnow(),
            encoding="utf-8",
            raw_content=normalized,
            metadata=metadata,
            access_record_id=f"AR-{doc_id}",
        )


def _decode_html(raw: bytes) -> tuple[str, str, str]:
    """识别 HTML 字节流的实际编码并解码。

    Returns:
        ``(decoded_text, original_encoding, charset_source)``,
        其中 ``charset_source`` 取值集合：``{"bom", "meta", "chardet", "default"}``.
    """
    if not raw:
        return "", "utf-8", "default"

    bom_result = _try_bom(raw)
    if bom_result is not None:
        bom_text, bom_encoding = bom_result
        return bom_text, bom_encoding, "bom"

    meta_encoding = _detect_meta_charset(raw)
    if meta_encoding is not None:
        text = raw.decode(meta_encoding, errors="strict")
        return text, meta_encoding, "meta"

    detected = chardet.detect(raw) or {}
    guess = (detected.get("encoding") or "").lower().replace("_", "-")
    if guess in _ALLOWED_ENCODINGS:
        text = raw.decode(guess, errors="strict")
        return text, guess, "chardet"

    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(enc, errors="strict")
        except UnicodeDecodeError:
            continue
        return text, enc, "chardet"

    msg = (
        f"could not decode html ({len(raw)} bytes) with allowed encodings "
        f"{sorted(_ALLOWED_ENCODINGS)}; chardet guess={guess!r}"
    )
    raise IngestError(msg)


def _try_bom(raw: bytes) -> tuple[str, str] | None:
    """按 BOM 嗅探编码；命中返回 ``(text, encoding)``, 未命中返回 ``None``。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    return None


def _detect_meta_charset(raw: bytes) -> str | None:
    """在文件首部扫描 ``<meta charset>`` 声明, 返回白名单内的编码名或 ``None``.

    说明:
      - 仅扫描前 ``_META_SCAN_BYTES`` 字节, 避免对 GB 级大文件做无谓正则。
      - 命中后必须校验该编码可合法解码首部字节, 否则视为误报。
    """
    head = raw[:_META_SCAN_BYTES]
    match = _META_CHARSET_RE.search(head)
    if match is None:
        return None
    declared = match.group(1).decode("ascii", errors="ignore").lower()
    declared = declared.replace("_", "-")
    if declared not in _ALLOWED_ENCODINGS:
        return None
    try:
        head.decode(declared, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return None
    return declared


def _stable_doc_id(payload: bytes) -> str:
    """基于标准化后的字节流生成稳定的 16-hex 字符 doc_id。"""
    return hashlib.sha256(payload).hexdigest()[:16]


__all__ = ["HtmlFileCollector"]


def _run_cli() -> int:
    """命令行入口: ``python -m p1_core.collectors.html --input <dir>``.

    打印每份文件的采集状态 (OK / ERROR), 最后汇总。
    返回 exit code: 0 = 全部成功, 1 = 出现 IngestError。
    """
    parser = argparse.ArgumentParser(
        prog="p1_core.collectors.html",
        description="HTML file collector (.html/.htm).",
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

    collector = HtmlFileCollector()
    success = 0
    errored = 0
    for result in collector.iter_directory(args.input, recursive=args.recursive):
        if isinstance(result, Exception):
            print(f"ERROR\t{result}", file=sys.stderr)
            errored += 1
        else:
            print(f"OK\t{result.source_uri}\t{result.doc_id}")
            success += 1
    print(f"# summary: success={success} errored={errored}", file=sys.stderr)
    return 0 if errored == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run_cli())
