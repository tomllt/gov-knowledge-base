"""HTML 文档解析器：保留标题、段落、列表、表格与图片语义。"""

from __future__ import annotations

from typing import ClassVar, Final

from selectolax.parser import HTMLParser, Node

from p1_core.exceptions import ParseError
from p1_core.models.enums import BlockType, DocumentFormat
from p1_core.models.heading import HeadingPath
from p1_core.models.parsed_document import ParsedBlock, ParsedDocument
from p1_core.models.raw_document import RawDocument
from p1_core.models.time_utils import utcnow
from p1_core.parsers.base import BaseParser

_NOISE: Final[frozenset[str]] = frozenset({"script", "style", "nav", "footer", "aside", "header"})
_HEADINGS: Final[frozenset[str]] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SPA_ROOTS: Final[tuple[str, ...]] = ("div#root", "div#app", "div#__nuxt", "div#__next")


class HtmlParser(BaseParser):
    """使用 selectolax 解析 HTML，不执行 JS 或下载资源。"""

    format: ClassVar[DocumentFormat] = DocumentFormat.HTML

    def parse(self, raw: RawDocument) -> ParsedDocument:
        """将 HTML 原始文档转换为解析块。"""
        self._ensure_format(raw)
        text = _decode(raw.raw_content, raw.encoding)
        try:
            dom = HTMLParser(text)
        except Exception as exc:
            raise ParseError(f"HTML DOM construction failed: {exc}") from exc  # noqa: TRY003
        render_required = _needs_render(dom)
        container = _container(dom)
        _remove_noise(container)
        state = _State(raw.doc_id)
        _walk(container, state)
        return ParsedDocument(
            raw_doc_id=raw.doc_id,
            parsed_at=utcnow(),
            format=DocumentFormat.HTML,
            blocks=tuple(state.blocks),
            render_required=render_required,
        )


class _State:
    """维护标题栈和解析块序列。"""

    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id
        self.headings: list[tuple[int, str]] = []
        self.blocks: list[ParsedBlock] = []

    def heading(self, level: int, text: str) -> None:
        """更新当前标题路径。"""
        self.headings = [(n, value) for n, value in self.headings if n < level]
        self.headings.append((level, _clean(text)))

    def add(self, kind: BlockType, text: str) -> None:
        """追加非空块。"""
        value = _clean(text)
        if not value:
            return
        path = HeadingPath(tuple(value for _, value in self.headings)) if self.headings else None
        self.blocks.append(
            ParsedBlock(
                block_id=f"{self.doc_id[:16]}-{len(self.blocks):04d}",
                block_type=kind,
                text=value,
                page=None,
                line_range=None,
                heading_path=path,
            )
        )


def _decode(raw: bytes, encoding: str) -> str:
    """宽容解码，乱码以 replacement character 保留。"""
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError as exc:
        raise ParseError(f"unsupported HTML encoding: {encoding!r}") from exc  # noqa: TRY003


def _container(dom: HTMLParser) -> Node:
    """按 main、article、body 顺序选择正文容器。"""
    for selector in ("main", "article", "body"):
        node = dom.css_first(selector)
        if node is not None:
            return node
    root = dom.root
    if root is None:
        raise ParseError("HTML document has no root node")  # noqa: TRY003
    return root


def _remove_noise(container: Node) -> None:
    """移除导航和装饰节点。"""
    for tag in _NOISE:
        for node in container.css(tag):
            node.decompose()


def _needs_render(dom: HTMLParser) -> bool:
    """识别文本极少的 React/Vue/Nuxt/Next 骨架页。"""
    body = dom.body or dom.root
    if body is None:
        return False
    text = body.text(separator=" ", strip=True) or ""
    return len(text) < 80 and any(dom.css_first(selector) is not None for selector in _SPA_ROOTS)


def _children(node: Node) -> list[Node]:
    """返回直接子节点，兼容 selectolax 的文本节点。"""
    result: list[Node] = []
    child = node.child
    while child is not None:
        result.append(child)
        child = child.next
    return result


def _walk(container: Node, state: _State) -> None:
    """按原始顺序递归提取块。"""
    pending: list[str] = []
    for node in _children(container):
        if node.tag == "-text":
            pending.append(node.text())
            continue
        _flush(pending, state)
        _handle(node, state)
    _flush(pending, state)


def _flush(pending: list[str], state: _State) -> None:
    """把块标签之间的裸文本合成段落。"""
    if pending:
        state.add(BlockType.PARAGRAPH, " ".join(pending))
        pending.clear()


def _handle(node: Node, state: _State) -> None:
    """处理一个 HTML 元素。"""
    tag = node.tag
    if tag in _HEADINGS:
        text = node.text(separator=" ", strip=True) or ""
        if text:
            state.heading(int(tag[1:]), text)
            state.add(BlockType.HEADING, text)
    elif tag == "p":
        state.add(BlockType.PARAGRAPH, node.text(separator=" ", strip=True) or "")
    elif tag == "table":
        state.add(BlockType.TABLE, _table_text(node))
    elif tag in {"ul", "ol"}:
        state.add(BlockType.LIST, _list_text(node))
    elif tag == "img":
        state.add(BlockType.IMAGE, node.attributes.get("alt", "") or "")
    elif tag == "br":
        return
    else:
        _walk(node, state)


def _list_text(node: Node) -> str:
    """把列表项聚合为一个列表块。"""
    return "\n".join(item.text(separator=" ", strip=True) for item in node.css("li"))


def _table_text(node: Node) -> str:
    """把完整表格序列化为单个管道分隔块，嵌套表格不拆块。"""
    rows = [
        [cell.text(separator=" ", strip=True) for cell in row.css("th, td")]
        for row in node.css("tr")
    ]
    rows = [row for row in rows if row]
    if not rows:
        return ""
    width = max(map(len, rows))
    padded = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(padded[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in padded[1:])
    return "\n".join(lines)


def _clean(text: str) -> str:
    """折叠 HTML 文本中的空白。"""
    return " ".join(text.split())


__all__ = ["HtmlParser"]
