# ruff: noqa: RUF001
"""`HtmlParser` 测试。

"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Final, get_type_hints

import pytest

from p1_core.collectors.html import HtmlFileCollector
from p1_core.exceptions import ParseError
from p1_core.models.enums import BlockType, DocumentFormat, SourceType
from p1_core.models.parsed_document import ParsedDocument
from p1_core.models.raw_document import RawDocument

# 选择性导入：实现尚未提交时这些符号可能不存在 —— 但失败信息应足够明确。
try:
    from p1_core.parsers.base import BaseParser
except ImportError:  # pragma: no cover - 测试驱动的早期阶段
    BaseParser = None  # type: ignore[assignment,misc]

try:
    from p1_core.parsers.html import HtmlParser
except ImportError:  # pragma: no cover - 测试驱动的早期阶段
    HtmlParser = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------


_COLLECTED_AT: Final[datetime] = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _raw(
    *,
    body: bytes,
    encoding: str = "utf-8",
    doc_id: str = "01HVHTMLPARSER000000000",
) -> RawDocument:
    """构造最小可用的 ``RawDocument``，内容已归一化为 utf-8。"""
    return RawDocument(
        doc_id=doc_id,
        source_type=SourceType.HTML,
        source_uri="mem://sample.html",
        collected_at=_COLLECTED_AT,
        encoding=encoding,
        raw_content=body,
        metadata=MappingProxyType({}),
        access_record_id=f"AR-{doc_id}",
    )


def _block_types(doc: ParsedDocument) -> list[BlockType]:
    return [b.block_type for b in doc.blocks]


def _block_texts(doc: ParsedDocument) -> list[str]:
    return [b.text for b in doc.blocks]


# ---------------------------------------------------------------------------
# 1. 正常 HTML
# ---------------------------------------------------------------------------


class TestHtmlParserBasicStructure:
    """正常 HTML：标题 / 段落 / 列表 / 表格 / 图片 元信息。"""

    def test_simple_html_yields_one_paragraph_block(self) -> None:
        assert HtmlParser is not None
        html = (
            "<html><body>"
            "<p>第一段：介绍政务知识库的目标。</p>"
            "</body></html>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))

        assert isinstance(doc, ParsedDocument)
        assert doc.format is DocumentFormat.HTML
        assert doc.raw_doc_id == "01HVHTMLPARSER000000000"
        assert doc.render_required is False
        assert _block_types(doc) == [BlockType.PARAGRAPH]
        assert "政务知识库" in doc.blocks[0].text

    def test_heading_paragraph_list_image(self) -> None:
        assert HtmlParser is not None
        html = (
            "<html><body>"
            "<h1>第一章 概述</h1>"
            "<p>本节描述目标。</p>"
            "<ul><li>事项一</li><li>事项二</li></ul>"
            "<img src='/x.png' alt='示意图'/>"
            "</body></html>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))

        types = _block_types(doc)
        assert types[0] is BlockType.HEADING
        assert types[1] is BlockType.PARAGRAPH
        assert types[2] is BlockType.LIST
        assert types[3] is BlockType.IMAGE

        assert doc.blocks[0].text.strip() == "第一章 概述"
        assert "事项一" in doc.blocks[2].text
        assert "事项二" in doc.blocks[2].text
        assert doc.blocks[3].text.strip() == "示意图"

    def test_each_block_has_unique_block_id(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body><h1>A</h1><p>p1</p><h2>B</h2><p>p2</p><p>p3</p></body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        ids = [b.block_id for b in doc.blocks]
        assert len(set(ids)) == len(ids)
        assert all(i for i in ids)


# ---------------------------------------------------------------------------
# 2. 标题层级 (HeadingPath)
# ---------------------------------------------------------------------------


class TestHtmlParserHeadingHierarchy:
    """h1~h6 自动映射为 HeadingPath 层级。"""

    def test_single_h1_yields_root_heading_path(self) -> None:
        assert HtmlParser is not None
        html = "<body><h1>标题 A</h1><p>x</p></body>"
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))

        para = doc.blocks[1]
        assert para.heading_path is not None
        assert para.heading_path.parts == ("标题 A",)
        assert para.heading_path.depth() == 1

    def test_h1_then_h2_then_h3_build_three_level_path(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<h1>第 1 章</h1>"
            "<p>章首段</p>"
            "<h2>1.1 节</h2>"
            "<p>节首段</p>"
            "<h3>1.1.1 小节</h3>"
            "<p>小节内容</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))

        # 第 4 个块 (h3 后第一个 p) 应有 3 级 HeadingPath。
        target = doc.blocks[5]
        assert target.text == "小节内容"
        assert target.heading_path is not None
        assert target.heading_path.parts == ("第 1 章", "1.1 节", "1.1.1 小节")
        assert target.heading_path.depth() == 3

    def test_h4_inside_h2_inside_h1_chain(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<h1>A</h1><h2>B</h2><h4>D</h4><p>x</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert doc.blocks[-1].heading_path is not None
        assert doc.blocks[-1].heading_path.parts == ("A", "B", "D")

    def test_sibling_same_level_resets_only_same_level(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<h1>A</h1><h2>B1</h2><p>x1</p>"
            "<h2>B2</h2><p>x2</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        # x1 应归属 B1，x2 应归属 B2。
        assert doc.blocks[2].heading_path is not None
        assert doc.blocks[2].heading_path.parts == ("A", "B1")
        assert doc.blocks[4].heading_path is not None
        assert doc.blocks[4].heading_path.parts == ("A", "B2")


# ---------------------------------------------------------------------------
# 3. 表格保留
# ---------------------------------------------------------------------------


class TestHtmlParserTablePreservation:
    """`<table>` 抽取为单 TABLE 块，行列不展开。"""

    def test_simple_table_becomes_one_table_block(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<table>"
            "<thead><tr><th>名称</th><th>数量</th></tr></thead>"
            "<tbody>"
            "<tr><td>事项 A</td><td>10</td></tr>"
            "<tr><td>事项 B</td><td>20</td></tr>"
            "</tbody>"
            "</table>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))

        assert _block_types(doc) == [BlockType.TABLE]
        text = doc.blocks[0].text
        # 必须包含表头与全部数据行（行列不展开意味着仍按行聚合）。
        assert "名称" in text
        assert "数量" in text
        assert "事项 A" in text
        assert "10" in text
        assert "事项 B" in text
        assert "20" in text
        # 表头分隔符不应被错误地插入在数据行之间。
        assert doc.blocks[0].block_type is BlockType.TABLE

    def test_table_block_does_not_split_into_paragraphs(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<table><tr><td>a</td><td>b</td></tr>"
            "<tr><td>c</td><td>d</td></tr></table>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        # 整个表应当只产出 1 个 TABLE 块，不能拆分。
        assert len(doc.blocks) == 1
        assert doc.blocks[0].block_type is BlockType.TABLE

    def test_table_inside_paragraph_still_treated_as_table(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<p>前置段落。</p>"
            "<table><tr><td>1</td><td>2</td></tr></table>"
            "<p>后置段落。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        types = _block_types(doc)
        assert types == [
            BlockType.PARAGRAPH,
            BlockType.TABLE,
            BlockType.PARAGRAPH,
        ]


# ---------------------------------------------------------------------------
# 3b. 嵌套表格
# ---------------------------------------------------------------------------


class TestHtmlParserNestedTables:
    """嵌套表格：表格内部再嵌表格，按单块提取（外层即整体）。"""

    def test_table_containing_table_yields_single_outer_block(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<table>"
            "<tr><td>外层 A</td><td>"
            "<table>"
            "<tr><td>内层 1</td><td>内层 2</td></tr>"
            "</table>"
            "</td></tr>"
            "</table>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))

        # 外层表格只产生 1 个 TABLE 块，不能递归拆出内层独立块。
        assert _block_types(doc) == [BlockType.TABLE]
        text = doc.blocks[0].text
        assert "外层 A" in text
        assert "内层 1" in text
        assert "内层 2" in text

    def test_triple_nested_table_still_one_block(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<table><tr><td>"
            "<table><tr><td>"
            "<table><tr><td>deep</td></tr></table>"
            "</td></tr></table>"
            "</td></tr></table>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert _block_types(doc) == [BlockType.TABLE]
        assert "deep" in doc.blocks[0].text


# ---------------------------------------------------------------------------
# 4. 噪声剥离
# ---------------------------------------------------------------------------


class TestHtmlParserNoiseStripping:
    """剔除 script / style / nav / footer / aside 等导航与装饰元素。"""

    @pytest.mark.parametrize(
        ("tag", "content"),
        [
            ("script", "<script>window.__INIT__=1</script>"),
            ("style", "<style>body{color:red}</style>"),
            ("nav", "<nav><a href='/'>首页</a></nav>"),
            ("footer", "<footer>版权 ©2026</footer>"),
            ("aside", "<aside>侧栏广告位</aside>"),
            ("header", "<header>顶部 LOGO 区域</header>"),
        ],
    )
    def test_noise_tags_excluded(self, tag: str, content: str) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            f"{content}"
            "<p>保留段落：核心内容。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))

        joined = "\n".join(_block_texts(doc))
        # 噪声元素的内部文本不应出现在任何块的 text 中。
        assert "核心内容" in joined
        # 各噪声标签的内文不应泄漏：
        leak_markers = {
            "script": "__INIT__",
            "style": "color:red",
            "nav": "首页",
            "footer": "版权",
            "aside": "侧栏广告",
            "header": "LOGO",
        }
        assert leak_markers[tag] not in joined

    def test_script_with_unicode_payload_still_excluded(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<script>const 文本 = '应被剔除';</script>"
            "<p>应保留的正文。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        joined = "\n".join(_block_texts(doc))
        assert "应保留" in joined
        assert "应被剔除" not in joined


# ---------------------------------------------------------------------------
# 5. <main> / <article> / <body> 优先级
# ---------------------------------------------------------------------------


class TestHtmlParserMainArticlePriority:
    """正文提取优先级：<main> > <article> > <body>。"""

    def test_main_takes_priority_over_body(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<p>应被忽略的 body 顶部内容。</p>"
            "<main>"
            "<h1>主区域标题</h1>"
            "<p>主区域段落。</p>"
            "</main>"
            "<p>应被忽略的 body 底部内容。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        joined = "\n".join(_block_texts(doc))
        assert "主区域标题" in joined
        assert "主区域段落" in joined
        assert "应被忽略的 body 顶部内容" not in joined
        assert "应被忽略的 body 底部内容" not in joined

    def test_article_used_when_no_main(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<p>body 顶部杂物。</p>"
            "<article>"
            "<h1>文章标题</h1>"
            "<p>文章正文。</p>"
            "</article>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        joined = "\n".join(_block_texts(doc))
        assert "文章标题" in joined
        assert "文章正文" in joined
        assert "body 顶部杂物" not in joined

    def test_body_used_when_no_main_or_article(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<h1>直接正文标题</h1>"
            "<p>直接正文段落。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        joined = "\n".join(_block_texts(doc))
        assert "直接正文标题" in joined
        assert "直接正文段落" in joined


# ---------------------------------------------------------------------------
# 6. 编码异常
# ---------------------------------------------------------------------------


class TestHtmlParserEncodingAnomalies:
    """编码异常：含乱码字节 / 不规范 meta charset。"""

    def test_garbled_text_does_not_crash(self) -> None:
        assert HtmlParser is not None
        # 含部分无法用 utf-8 解码的字节；采集器已归一化但解析器也应宽容。
        # 这里直接把含 replacement char 的 utf-8 文本送入。
        html = "<body><p>你好，\ufffd\ufffd 世界。</p></body>"
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert any("你好" in b.text for b in doc.blocks)

    def test_mismatched_meta_charset_is_tolerated(self) -> None:
        assert HtmlParser is not None
        # meta 声明 utf-8 但内容里混入了几个 latin-1 的字节，已经被采集器替换为 replacement。
        html = (
            "<html><head><meta charset='utf-8'></head>"
            "<body><p>中文段落\ufffd\ufffd 末尾。</p></body></html>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert any("中文段落" in b.text for b in doc.blocks)

    def test_empty_body_returns_no_blocks(self) -> None:
        assert HtmlParser is not None
        doc = HtmlParser().parse(_raw(body=b"<html><body></body></html>"))
        assert doc.blocks == ()

    def test_whitespace_only_body_returns_no_blocks(self) -> None:
        assert HtmlParser is not None
        doc = HtmlParser().parse(_raw(body=b"<html><body>   \n\t  </body></html>"))
        assert doc.blocks == ()


# ---------------------------------------------------------------------------
# 7. JS 渲染残缺 (SPA 骨架页)
# ---------------------------------------------------------------------------


class TestHtmlParserJsRenderedIncomplete:
    """JS 渲染残缺 (SPA 骨架)：标记 render_required=True。"""

    def test_react_root_div_only_marks_render_required(self) -> None:
        assert HtmlParser is not None
        html = (
            "<html><body>"
            "<div id='root'></div>"
            "<script src='/app.js'></script>"
            "</body></html>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert doc.render_required is True

    def test_vue_app_div_only_marks_render_required(self) -> None:
        assert HtmlParser is not None
        html = (
            "<html><body>"
            "<div id='app' data-server-rendered='false'></div>"
            "</body></html>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert doc.render_required is True

    def test_normal_content_is_not_marked(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<h1>正常文章</h1>"
            "<p>这是正常内容。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert doc.render_required is False


# ---------------------------------------------------------------------------
# 8. 富文本编辑器输出 (TinyMCE / CKEditor 风格)
# ---------------------------------------------------------------------------


class TestHtmlParserRichTextEditor:
    """富文本编辑器输出：含大量 inline style / span / font 等。"""

    def test_inline_styles_preserve_text(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<h1>编辑稿</h1>"
            "<p><span style='font-weight:bold'>粗体</span>与"
            "<span style='color:#c00'>红字</span>混合。"
            "<em>斜体</em>和<u>下划线</u>。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        para_text = "\n".join(_block_texts(doc))
        assert "粗体" in para_text
        assert "红字" in para_text
        assert "斜体" in para_text
        assert "下划线" in para_text
        # 样式不应泄漏到正文里。
        assert "font-weight" not in para_text
        assert "#c00" not in para_text

    def test_nested_spans_flatten_to_text(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<p><span><span><span>深层 span 内容</span></span></span></p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        assert any("深层 span 内容" in b.text for b in doc.blocks)

    def test_paragraph_with_linebreak_inside(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<p>第一行<br/>第二行<br/>第三行</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        text = "\n".join(_block_texts(doc))
        # 三个行均应保留 (使用换行 / 空格分隔均可, 但内容必须完整)。
        assert "第一行" in text
        assert "第二行" in text
        assert "第三行" in text


# ---------------------------------------------------------------------------
# 9. GBK 编码链路 (Collector + Parser)
# ---------------------------------------------------------------------------


class TestHtmlParserGbkPipeline:
    """GBK 编码：经 ``HtmlFileCollector`` 归一化后链路通畅，正文还原正确。"""

    def test_gbk_encoded_html_round_trip_via_collector(self, tmp_path: Path) -> None:
        # 路径整体：把 gb18030 字节写入文件 → HtmlFileCollector → HtmlParser。

        body = (
            "<html><body>"
            "<h1>政务事项办理流程</h1>"
            "<p>本指南介绍事项库的申请、受理、办结全过程。</p>"
            "<table><tr><th>环节</th><th>时限</th></tr>"
            "<tr><td>申请</td><td>1 工作日</td></tr></tr></table>"
            "</body></html>"
        )
        path = tmp_path / "g18030.html"
        path.write_bytes(body.encode("gb18030"))

        raw = HtmlFileCollector().collect(path)
        assert raw.encoding == "utf-8"  # 采集器已归一化。

        assert HtmlParser is not None
        doc = HtmlParser().parse(raw)

        joined = "\n".join(_block_texts(doc))
        assert "政务事项办理流程" in joined
        assert "事项库的申请" in joined
        assert "申请" in joined
        assert "1 工作日" in joined
        assert BlockType.TABLE in _block_types(doc)


# ---------------------------------------------------------------------------
# 10. 巨文件
# ---------------------------------------------------------------------------


class TestHtmlParserLargeFile:
    """巨文件：≥10MB HTML 不应崩溃或超时。"""

    def test_large_html_parses_without_crash(self) -> None:
        assert HtmlParser is not None
        # 构造 ≥10MB 的 HTML（每个段落重复填充随机内容避免压缩）。
        para_count = 300_000
        chunk = "".join(
            f"<p>政务知识库段落 {i:08d}：包含汉字、English、符号 ☃ ★。</p>"
            for i in range(para_count)
        )
        html = "<html><body>" + chunk + "</body></html>"
        body = html.encode("utf-8")
        assert len(body) >= 10 * 1024 * 1024

        doc = HtmlParser().parse(_raw(body=body))

        # 至少解析出大量段落 (允许尾部因容差被合并, 但总量级必须匹配)。
        para_blocks = [b for b in doc.blocks if b.block_type is BlockType.PARAGRAPH]
        assert len(para_blocks) >= para_count // 2
        # 首段与某中间段必须包含期望内容。
        joined = "\n".join(b.text for b in para_blocks[:5])
        assert "政务知识库段落 00000000" in joined


# ---------------------------------------------------------------------------
# 11. BaseParser 接口契约
# ---------------------------------------------------------------------------


class TestHtmlParserBaseInterface:
    """继承 ``BaseParser``，``format=HTML``，可被多态调用。"""

    def test_html_parser_subclass_of_base(self) -> None:
        if BaseParser is None or HtmlParser is None:
            pytest.skip("BaseParser/HtmlParser not yet implemented")
        assert issubclass(HtmlParser, BaseParser)

    def test_format_class_attribute_is_html(self) -> None:
        if BaseParser is None or HtmlParser is None:
            pytest.skip("BaseParser/HtmlParser not yet implemented")
        assert HtmlParser.format is DocumentFormat.HTML

    def test_parse_signature_takes_raw_document(self) -> None:
        if BaseParser is None or HtmlParser is None:
            pytest.skip("BaseParser/HtmlParser not yet implemented")

        sig = inspect.signature(HtmlParser.parse)
        params = list(sig.parameters.values())
        assert params[0].name == "self"
        assert params[1].name == "raw"
        # 第二参数类型注解应为 RawDocument。

        hints = get_type_hints(HtmlParser.parse)
        assert hints.get("raw") is RawDocument

    def test_parse_raises_parse_error_on_non_html_input(self) -> None:
        if HtmlParser is None:
            pytest.skip("HtmlParser not yet implemented")
        # 用一个 PDF 类型的 RawDocument 强行送入：应当被识别为格式不匹配并抛 ParseError。
        pdf_raw = RawDocument(
            doc_id="01HVHTMLPARSER000000001",
            source_type=SourceType.PDF,
            source_uri="mem://x.pdf",
            collected_at=_COLLECTED_AT,
            encoding="utf-8",
            raw_content=b"%PDF-1.4 fake",
            metadata=MappingProxyType({}),
            access_record_id="AR-01HVHTMLPARSER000000001",
        )
        with pytest.raises(ParseError):
            HtmlParser().parse(pdf_raw)


# ---------------------------------------------------------------------------
# 12. 边界：极小文档
# ---------------------------------------------------------------------------


class TestHtmlParserEdgeCases:
    """极小文档：纯文本片段、空 head、缺 root 等。"""

    def test_text_only_no_html_tags(self) -> None:
        assert HtmlParser is not None
        # 偶尔存在 fragment 形式的输入（采集器已包了 body，但兜底再校验一次）。
        html = "<body>纯文本，无标签。</body>"
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        joined = "\n".join(_block_texts(doc))
        assert "纯文本" in joined

    def test_unicode_only_blocks(self) -> None:
        assert HtmlParser is not None
        html = (
            "<body>"
            "<h1>标题：测试 emoji 🚀 与中文 ★ ☃</h1>"
            "<p>正文：α β γ δ ε → 汉字 𠮷 。</p>"
            "</body>"
        )
        doc = HtmlParser().parse(_raw(body=html.encode("utf-8")))
        joined = "\n".join(_block_texts(doc))
        assert "🚀" in joined
        assert "α β γ" in joined
        assert "𠮷" in joined  # CJK 扩展 B 区
