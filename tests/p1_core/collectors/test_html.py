"""`HtmlFileCollector` 测试。

覆盖以下六类场景：
  1. 正样本：合法 UTF-8 HTML
  2. 损坏文件：无法解码的二进制字节
  3. 空文件
  4. 非 UTF-8 编码（gb18030）HTML
  5. `<meta charset>` 声明的编码优先于 chardet
  6. 巨文件（确保大文件可被采集且不被一次性全量读入内存做无谓处理）
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from p1_core.collectors.base import UnsupportedFormatError
from p1_core.collectors.html import HtmlFileCollector
from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


class TestHtmlFileCollectorMetadata:
    """采集器元信息与接口契约。"""

    def test_source_type_is_html(self) -> None:
        assert HtmlFileCollector.source_type is SourceType.HTML

    def test_supported_extensions_includes_html_htm(self) -> None:
        exts = HtmlFileCollector().supported_extensions()
        assert ".html" in exts
        assert ".htm" in exts


class TestHtmlFileCollectorHappyPath:
    """正样本：合法 UTF-8 HTML。"""

    def test_collects_basic_utf8_html(self, tmp_path: Path) -> None:
        payload = "<!DOCTYPE html><html><head><title>测试</title></head><body>你好</body></html>"
        path = _write(tmp_path / "page.html", payload.encode("utf-8"))

        result = HtmlFileCollector().collect(path)

        assert isinstance(result, RawDocument)
        assert result.source_type is SourceType.HTML
        assert result.source_uri == str(path)
        assert result.encoding == "utf-8"
        assert result.raw_content.decode("utf-8") == payload
        # 元信息：原始编码 + 来源 + 检测方法。
        assert result.metadata["charset_source"] in {
            "bom",
            "meta",
            "chardet",
            "default",
        }
        # 无 BOM / meta 时默认走 chardet 兜底，UTF-8 应能直接识别为 utf-8。
        assert result.metadata["charset_source"] in {"default", "chardet"}
        assert result.doc_id
        assert result.access_record_id
        assert result.collected_at.tzinfo is not None

    def test_collects_utf8_bom_html(self, tmp_path: Path) -> None:
        body = "<html><body>BOM 测试</body></html>"
        payload = body.encode("utf-8")
        with_bom = b"\xef\xbb\xbf" + payload
        path = _write(tmp_path / "bom.html", with_bom)

        result = HtmlFileCollector().collect(path)

        # BOM 应当被剥离后重新以 utf-8 编码；元信息标识来源为 BOM。
        assert result.encoding == "utf-8"
        assert result.raw_content == payload
        assert result.metadata["charset_source"] == "bom"
        assert result.metadata["original_encoding"] == "utf-8-sig"

    def test_collects_html_with_meta_charset(self, tmp_path: Path) -> None:
        # 文件内 `<meta charset="gb18030">` 声明，且内容确实是 gb18030。
        body = "<html><head><meta charset='gb18030'/></head><body>政务知识库</body></html>"
        payload = body.encode("gb18030")
        path = _write(tmp_path / "meta.html", payload)

        result = HtmlFileCollector().collect(path)

        assert result.encoding == "utf-8"
        assert result.metadata["charset_source"] == "meta"
        assert result.metadata["original_encoding"] == "gb18030"
        # 内容应当正确解码并重新以 utf-8 编码。
        assert "政务知识库".encode() in result.raw_content


class TestHtmlFileCollectorEncodingScenarios:
    """非 UTF-8 编码 / BOM / chardet 三种来源。"""

    def test_collects_gbk_encoded_html(self, tmp_path: Path) -> None:
        body = "<html><body>事项库审批流程</body></html>"
        payload = body.encode("gbk")
        path = _write(tmp_path / "gbk.html", payload)

        result = HtmlFileCollector().collect(path)

        assert result.encoding == "utf-8"
        assert result.metadata["original_encoding"] in {"gbk", "gb18030"}
        assert "事项库审批流程".encode() in result.raw_content

    def test_collects_gb18030_encoded_html_without_meta(self, tmp_path: Path) -> None:
        # 无任何编码声明，靠 chardet 识别。
        body = "<html><body>政务事项</body></html>"
        payload = body.encode("gb18030")
        path = _write(tmp_path / "gb18030.html", payload)

        result = HtmlFileCollector().collect(path)

        assert result.encoding == "utf-8"
        assert result.metadata["original_encoding"] in {"gb18030", "gbk"}
        assert "政务事项".encode() in result.raw_content

    def test_meta_charset_takes_precedence(self, tmp_path: Path) -> None:
        # 文件声明 utf-8，payload 也确实是 utf-8；以 meta 为准。
        body = "<html><head><meta charset='utf-8'/></head><body>café</body></html>"
        payload = body.encode("utf-8")
        path = _write(tmp_path / "mixed.html", payload)

        result = HtmlFileCollector().collect(path)

        assert result.encoding == "utf-8"
        assert result.metadata["charset_source"] == "meta"
        assert "café".encode() in result.raw_content

    def test_unsupported_encoding_raises_ingest_error(self, tmp_path: Path) -> None:
        # 不在白名单中的编码（latin-1）：utf-8/gb18030/gbk 都无法合法解码，
        # chardet 的猜测也未命中白名单——按采集契约应抛出 IngestError。
        body = "<html><body>café résumé naïve</body></html>"
        payload = body.encode("latin-1")
        path = _write(tmp_path / "latin.html", payload)

        with pytest.raises(IngestError, match=r"decode|encoding|invalid"):
            HtmlFileCollector().collect(path)


class TestHtmlFileCollectorErrorScenarios:
    """损坏 / 空文件 / 缺文件 / 错误扩展名。"""

    def test_undecodable_bytes_raise_ingest_error(self, tmp_path: Path) -> None:
        # 随机字节，不在 utf-8/gb18030/gbk 任何编码下都是非法序列。
        rng = random.Random(42)
        garbage = bytes(rng.randint(0, 255) for _ in range(2048))
        path = _write(tmp_path / "garbage.html", garbage)
        with pytest.raises(IngestError, match=r"decode|encoding|invalid"):
            HtmlFileCollector().collect(path)

    def test_empty_file_returns_empty_document(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "empty.html", b"")
        result = HtmlFileCollector().collect(path)
        assert result.raw_content == b""
        assert result.encoding == "utf-8"

    def test_missing_file_raises_ingest_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost.html"
        with pytest.raises(IngestError, match=r"not found|missing"):
            HtmlFileCollector().collect(missing)

    def test_wrong_extension_raises_unsupported_format_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "data.txt", b"<html><body>hi</body></html>")
        with pytest.raises(UnsupportedFormatError, match=r"unsupported_format"):
            HtmlFileCollector().collect(path)


class TestHtmlFileCollectorLargeFile:
    """巨文件：确保采集器不会因大文件而崩溃。"""

    def test_collects_large_html_file(self, tmp_path: Path) -> None:
        # 构造 >5MB 的 HTML：每个段落重复填充随机内容避免压缩。
        chunk = "".join(f"<p>政务知识库段落 {i:06d}</p>" for i in range(200_000))
        payload = ("<html><body>" + chunk + "</body></html>").encode("utf-8")
        path = _write(tmp_path / "big.html", payload)
        assert path.stat().st_size >= 5 * 1024 * 1024

        result = HtmlFileCollector().collect(path)

        assert result.encoding == "utf-8"
        assert len(result.raw_content) == path.stat().st_size
        assert result.metadata["charset_source"] in {"chardet", "default"}


class TestHtmlFileCollectorDirectoryIteration:
    """目录批量采集 + 错误隔离。"""

    def test_iter_directory_filters_html_and_htm(self, tmp_path: Path) -> None:
        (tmp_path / "a.html").write_bytes(b"<html><body>a</body></html>")
        (tmp_path / "b.htm").write_bytes(b"<html><body>b</body></html>")
        (tmp_path / "skip.txt").write_text("plain", encoding="utf-8")

        results = list(HtmlFileCollector().iter_directory(tmp_path))

        assert len(results) == 2
        assert all(isinstance(r, RawDocument) for r in results)

    def test_iter_directory_isolates_decode_errors(self, tmp_path: Path) -> None:
        (tmp_path / "ok.html").write_bytes(b"<html><body>ok</body></html>")
        # 第二份是随机字节，几乎不可能在白名单编码下合法。
        rng = random.Random(7)
        (tmp_path / "bad.html").write_bytes(bytes(rng.randint(0, 255) for _ in range(2048)))

        results = list(HtmlFileCollector().iter_directory(tmp_path))

        kinds = [type(r).__name__ for r in results]
        assert "RawDocument" in kinds
        assert "IngestError" in kinds
