"""
DOCX → GFM Markdown AST parser.

Reads word/document.xml from a .docx archive and produces an AST whose nodes
are defined in ast_nodes.py.  Every node carries an `xpath` attribute that
points back to the originating element in word/document.xml.

Design notes:
  - We use stdlib xml.etree.ElementTree for XML parsing.  lxml would give us
    getpath() for free, but we compute XPaths manually so there's no hard dep.
  - Style inheritance is resolved from word/styles.xml.
  - List detection uses word/numbering.xml to determine bullet vs ordered.
  - Relationships (hyperlinks, images) are resolved from
    word/_rels/document.xml.rels.

Usage::

    from extradocx.parser import DocxParser

    parser = DocxParser("path/to/file.docx")
    doc = parser.parse()          # returns ast_nodes.Document
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from extradocx.ast_nodes import (
    BlockNode,
    BlockQuote,
    BulletList,
    CodeBlock,
    Document,
    Heading,
    Image,
    InlineNode,
    LineBreak,
    Link,
    ListItem,
    OrderedList,
    Paragraph,
    RawBlock,
    SoftBreak,
    Table,
    TableCell,
    TableRow,
    TextRun,
    ThematicBreak,
)

# ---------------------------------------------------------------------------
# XML namespace map used throughout this file
# ---------------------------------------------------------------------------

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "v": "urn:schemas-microsoft-com:vml",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}


def _tag(ns: str, local: str) -> str:
    """Return Clark-notation tag string, e.g. '{...ns...}local'."""
    return f"{{{NS[ns]}}}{local}"


# ---------------------------------------------------------------------------
# XPath helper – stdlib ET doesn't give getpath() so we track position manually
# ---------------------------------------------------------------------------


def _element_xpath(path_parts: list[tuple[str, int]]) -> str:
    """Build an XPath string from a list of (clark-tag, 1-based-index) pairs."""
    parts: list[str] = []
    for clark, idx in path_parts:
        # Simplify clark notation → prefix:local for readability
        local = clark
        for prefix, uri in NS.items():
            uri_braced = f"{{{uri}}}"
            if clark.startswith(uri_braced):
                local = f"{prefix}:{clark[len(uri_braced):]}"
                break
        parts.append(f"{local}[{idx}]")
    return "/" + "/".join(parts)


# ---------------------------------------------------------------------------
# Style resolution helpers
# ---------------------------------------------------------------------------


@dataclass
class StyleInfo:
    """Resolved style properties for a paragraph or character style."""

    style_id: str = ""
    name: str = ""
    # Heading level 1-6 if this is a heading style, else None
    heading_level: Optional[int] = None
    is_code: bool = False
    is_quote: bool = False
    is_title: bool = False       # Document title → rendered as h1
    is_bullet_list: bool = False # "List Bullet" family → bullet list item
    is_ordered_list: bool = False # "List Number" family → ordered list item
    list_depth: int = 0          # 0 = top level; 1 = nested once; etc.


_HEADING_RE = re.compile(r"heading\s*(\d)", re.IGNORECASE)
_CODE_NAMES = {"Code", "CodeBlock", "Code Block", "Verbatim", "Preformatted"}
_QUOTE_NAMES = {"Quote", "Intense Quote", "Block Text", "Blockquote"}
# Matches "List Bullet", "List Bullet 2", "List Bullet 3"
_LIST_BULLET_RE = re.compile(r"list bullet\s*(\d?)", re.IGNORECASE)
# Matches "List Number", "List Number 2", "List Number 3"
_LIST_NUMBER_RE = re.compile(r"list number\s*(\d?)", re.IGNORECASE)


def _parse_styles(xml_bytes: bytes) -> dict[str, StyleInfo]:
    """Parse word/styles.xml → map of styleId → StyleInfo."""
    styles: dict[str, StyleInfo] = {}
    root = ET.fromstring(xml_bytes)
    for style_el in root.findall(f".//{_tag('w','style')}"):
        sid = style_el.get(_tag("w", "styleId"), "")
        if not sid:
            continue
        name_el = style_el.find(_tag("w", "name"))
        name = name_el.get(_tag("w", "val"), "") if name_el is not None else sid

        info = StyleInfo(style_id=sid, name=name)
        m = _HEADING_RE.match(name)
        if m:
            level = int(m.group(1))
            info.heading_level = min(level, 6)  # GFM max is h6
        elif name.lower() in ("title",):
            info.is_title = True
        elif name in _CODE_NAMES:
            info.is_code = True
        elif name in _QUOTE_NAMES:
            info.is_quote = True
        else:
            mb = _LIST_BULLET_RE.match(name)
            if mb:
                info.is_bullet_list = True
                depth_str = mb.group(1)
                info.list_depth = max(0, int(depth_str) - 1) if depth_str else 0
            else:
                mn = _LIST_NUMBER_RE.match(name)
                if mn:
                    info.is_ordered_list = True
                    depth_str = mn.group(1)
                    info.list_depth = max(0, int(depth_str) - 1) if depth_str else 0

        styles[sid] = info
    return styles


# ---------------------------------------------------------------------------
# Numbering resolution
# ---------------------------------------------------------------------------


@dataclass
class NumFmt:
    """Resolved numbering info for a numId+ilvl combination."""

    is_ordered: bool  # True = decimal/alpha/roman; False = bullet
    start_val: int = 1


def _parse_numbering(xml_bytes: bytes) -> dict[tuple[str, str], NumFmt]:
    """Parse word/numbering.xml → {(numId, ilvl): NumFmt}."""
    result: dict[tuple[str, str], NumFmt] = {}
    root = ET.fromstring(xml_bytes)

    # Collect abstractNum definitions
    abstract: dict[str, dict[str, NumFmt]] = {}
    for abs_el in root.findall(f".//{_tag('w','abstractNum')}"):
        abs_id = abs_el.get(_tag("w", "abstractNumId"), "")
        levels: dict[str, NumFmt] = {}
        for lvl in abs_el.findall(f".//{_tag('w','lvl')}"):
            ilvl = lvl.get(_tag("w", "ilvl"), "0")
            fmt_el = lvl.find(_tag("w", "numFmt"))
            start_el = lvl.find(_tag("w", "start"))
            fmt_val = fmt_el.get(_tag("w", "val"), "bullet") if fmt_el is not None else "bullet"
            start_val = int(start_el.get(_tag("w", "val"), "1")) if start_el is not None else 1
            is_ordered = fmt_val not in ("bullet", "none", "")
            levels[ilvl] = NumFmt(is_ordered=is_ordered, start_val=start_val)
        abstract[abs_id] = levels

    # Map numId → abstractNumId
    for num_el in root.findall(f".//{_tag('w','num')}"):
        num_id = num_el.get(_tag("w", "numId"), "")
        abs_ref = num_el.find(_tag("w", "abstractNumId"))
        if abs_ref is None:
            continue
        abs_id = abs_ref.get(_tag("w", "val"), "")
        levels = abstract.get(abs_id, {})
        for ilvl, fmt in levels.items():
            result[(num_id, ilvl)] = fmt

    return result


# ---------------------------------------------------------------------------
# Relationship resolution
# ---------------------------------------------------------------------------


def _parse_rels(xml_bytes: bytes) -> dict[str, str]:
    """Parse word/_rels/document.xml.rels → {rId: target}."""
    rels: dict[str, str] = {}
    root = ET.fromstring(xml_bytes)
    for rel in root:
        rid = rel.get("Id", "")
        target = rel.get("Target", "")
        if rid:
            rels[rid] = target
    return rels


# ---------------------------------------------------------------------------
# Run properties helper
# ---------------------------------------------------------------------------


def _run_is_bold(rpr: Optional[ET.Element]) -> bool:
    if rpr is None:
        return False
    b = rpr.find(_tag("w", "b"))
    if b is None:
        return False
    val = b.get(_tag("w", "val"), "true")
    return val.lower() not in ("false", "0", "off")


def _run_is_italic(rpr: Optional[ET.Element]) -> bool:
    if rpr is None:
        return False
    i = rpr.find(_tag("w", "i"))
    if i is None:
        return False
    val = i.get(_tag("w", "val"), "true")
    return val.lower() not in ("false", "0", "off")


def _run_is_underline(rpr: Optional[ET.Element]) -> bool:
    if rpr is None:
        return False
    u = rpr.find(_tag("w", "u"))
    if u is None:
        return False
    val = u.get(_tag("w", "val"), "single")
    return val.lower() not in ("none", "false", "0")


def _run_is_strike(rpr: Optional[ET.Element]) -> bool:
    if rpr is None:
        return False
    return rpr.find(_tag("w", "strike")) is not None or rpr.find(_tag("w", "dstrike")) is not None


def _run_is_code(rpr: Optional[ET.Element]) -> bool:
    """Detect monospace / code font by rStyle or font name."""
    if rpr is None:
        return False
    rstyle = rpr.find(_tag("w", "rStyle"))
    if rstyle is not None:
        val = rstyle.get(_tag("w", "val"), "")
        if val.lower() in ("verbatimchar", "code", "codechar", "inlinecode"):
            return True
    fonts = rpr.find(_tag("w", "rFonts"))
    if fonts is not None:
        for attr in fonts.attrib.values():
            if any(m in attr.lower() for m in ("courier", "consolas", "mono", "code")):
                return True
    return False


def _run_is_super(rpr: Optional[ET.Element]) -> bool:
    if rpr is None:
        return False
    vert = rpr.find(_tag("w", "vertAlign"))
    return vert is not None and vert.get(_tag("w", "val"), "") == "superscript"


def _run_is_sub(rpr: Optional[ET.Element]) -> bool:
    if rpr is None:
        return False
    vert = rpr.find(_tag("w", "vertAlign"))
    return vert is not None and vert.get(_tag("w", "val"), "") == "subscript"


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


class DocxParser:
    """Parses a .docx file into a GFM-oriented AST.

    Parameters
    ----------
    docx_path:
        Path to the .docx file.
    """

    def __init__(self, docx_path: str | Path) -> None:
        self._path = Path(docx_path)
        self._styles: dict[str, StyleInfo] = {}
        self._numbering: dict[tuple[str, str], NumFmt] = {}
        self._rels: dict[str, str] = {}
        # Track sibling position for XPath generation: stack of {tag: count}
        self._position_stack: list[dict[str, int]] = []
        # Running path segments for XPath
        self._xpath_parts: list[tuple[str, int]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> Document:
        """Parse the docx and return the root Document AST node."""
        with zipfile.ZipFile(self._path) as zf:
            names = zf.namelist()

            # Load support files
            if "word/styles.xml" in names:
                self._styles = _parse_styles(zf.read("word/styles.xml"))
            if "word/numbering.xml" in names:
                self._numbering = _parse_numbering(zf.read("word/numbering.xml"))
            if "word/_rels/document.xml.rels" in names:
                self._rels = _parse_rels(zf.read("word/_rels/document.xml.rels"))

            doc_xml = zf.read("word/document.xml")

        root = ET.fromstring(doc_xml)
        body = root.find(_tag("w", "body"))
        if body is None:
            return Document(source_path=str(self._path))

        body_xpath = "/w:document[1]/w:body[1]"
        children = self._parse_body(body, body_xpath)
        return Document(
            children=children,
            xpath=body_xpath,
            source_path=str(self._path),
        )

    # ------------------------------------------------------------------
    # Body-level parsing
    # ------------------------------------------------------------------

    def _parse_body(self, body: ET.Element, body_xpath: str) -> list[BlockNode]:
        """Convert <w:body> children into a list of BlockNodes.

        Lists are detected by scanning consecutive paragraphs that share a
        numId and grouping them into BulletList / OrderedList nodes.
        """
        raw_blocks = self._collect_raw_blocks(body, body_xpath)
        return self._group_lists(raw_blocks)

    def _collect_raw_blocks(
        self, parent: ET.Element, parent_xpath: str
    ) -> list[BlockNode]:
        """Convert each direct child of *parent* to a BlockNode (ungrouped)."""
        blocks: list[BlockNode] = []
        tag_counts: dict[str, int] = {}

        for child in parent:
            tag = child.tag
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            idx = tag_counts[tag]
            # Compute simple local tag name for XPath
            local = tag
            for prefix, uri in NS.items():
                uri_braced = f"{{{uri}}}"
                if tag.startswith(uri_braced):
                    local = f"{prefix}:{tag[len(uri_braced):]}"
                    break
            child_xpath = f"{parent_xpath}/{local}[{idx}]"

            if tag == _tag("w", "p"):
                block = self._parse_paragraph(child, child_xpath)
                if block is not None:
                    blocks.append(block)
            elif tag == _tag("w", "tbl"):
                blocks.append(self._parse_table(child, child_xpath))
            elif tag == _tag("w", "sdt"):
                # Structured document tag – descend into content
                content = child.find(_tag("w", "sdtContent"))
                if content is not None:
                    inner = self._collect_raw_blocks(content, child_xpath + "/w:sdtContent[1]")
                    blocks.extend(inner)
            # w:sectPr and other body-level elements are silently skipped

        return blocks

    # ------------------------------------------------------------------
    # Paragraph parsing
    # ------------------------------------------------------------------

    def _parse_paragraph(
        self, para: ET.Element, xpath: str
    ) -> Optional[BlockNode]:
        """Convert a <w:p> element to the appropriate BlockNode."""
        ppr = para.find(_tag("w", "pPr"))
        style_id = ""
        num_id: Optional[str] = None
        ilvl: str = "0"

        if ppr is not None:
            pstyle = ppr.find(_tag("w", "pStyle"))
            if pstyle is not None:
                style_id = pstyle.get(_tag("w", "val"), "")
            numpr = ppr.find(_tag("w", "numPr"))
            if numpr is not None:
                nid_el = numpr.find(_tag("w", "numId"))
                ilvl_el = numpr.find(_tag("w", "ilvl"))
                if nid_el is not None:
                    num_id = nid_el.get(_tag("w", "val"), None)
                if ilvl_el is not None:
                    ilvl = ilvl_el.get(_tag("w", "val"), "0")

        style_info = self._styles.get(style_id)
        inlines = self._parse_inlines(para, xpath)

        # Skip truly empty paragraphs (no text at all)
        if not inlines:
            # Check for page break
            for r in para.findall(f".//{_tag('w','r')}"):
                br = r.find(_tag("w", "br"))
                if br is not None:
                    br_type = br.get(_tag("w", "type"), "")
                    if br_type == "page":
                        return ThematicBreak(xpath=xpath)
            return None

        # List paragraph via numPr (explicit numbering in XML)
        if num_id and num_id != "0":
            fmt = self._numbering.get((num_id, ilvl))
            return _ListParagraph(
                inlines=inlines,
                xpath=xpath,
                style_id=style_id,
                num_id=num_id,
                ilvl=int(ilvl),
                is_ordered=fmt.is_ordered if fmt else False,
                start_val=fmt.start_val if fmt else 1,
            )

        if style_info is not None:
            if style_info.heading_level is not None:
                return Heading(
                    level=style_info.heading_level,
                    children=inlines,
                    xpath=xpath,
                    style_id=style_id,
                )
            if style_info.is_title:
                # Document title → treat as h1
                return Heading(level=1, children=inlines, xpath=xpath, style_id=style_id)
            if style_info.is_code:
                text = "".join(
                    t.text for t in inlines if isinstance(t, TextRun)
                )
                return CodeBlock(code=text, xpath=xpath)
            if style_info.is_quote:
                inner_para = Paragraph(children=inlines, xpath=xpath, style_id=style_id)
                return BlockQuote(children=[inner_para], xpath=xpath)
            # List via named style (e.g. ListBullet, ListNumber from python-docx)
            if style_info.is_bullet_list:
                return _ListParagraph(
                    inlines=inlines,
                    xpath=xpath,
                    style_id=style_id,
                    num_id="",
                    ilvl=style_info.list_depth,
                    is_ordered=False,
                )
            if style_info.is_ordered_list:
                return _ListParagraph(
                    inlines=inlines,
                    xpath=xpath,
                    style_id=style_id,
                    num_id="",
                    ilvl=style_info.list_depth,
                    is_ordered=True,
                )

        return Paragraph(children=inlines, xpath=xpath, style_id=style_id)

    # ------------------------------------------------------------------
    # Inline parsing
    # ------------------------------------------------------------------

    def _parse_inlines(self, para: ET.Element, para_xpath: str) -> list[InlineNode]:
        """Extract inline nodes from a <w:p> element."""
        inlines: list[InlineNode] = []
        run_counts: dict[str, int] = {}

        for child in para:
            tag = child.tag
            run_counts[tag] = run_counts.get(tag, 0) + 1
            idx = run_counts[tag]
            local = self._clark_to_prefix(tag)
            child_xpath = f"{para_xpath}/{local}[{idx}]"

            if tag == _tag("w", "r"):
                inlines.extend(self._parse_run(child, child_xpath))
            elif tag == _tag("w", "hyperlink"):
                inlines.append(self._parse_hyperlink(child, child_xpath))
            elif tag == _tag("w", "ins"):
                # Track-change insertion – treat as normal content
                for sub in child:
                    if sub.tag == _tag("w", "r"):
                        inlines.extend(self._parse_run(sub, child_xpath))
            elif tag == _tag("w", "del"):
                # Track-change deletion – skip deleted text
                pass
            elif tag == _tag("w", "bookmarkStart"):
                pass  # skip
            elif tag == _tag("w", "bookmarkEnd"):
                pass
            # Other inline elements (smart tags, etc.) are skipped silently

        return inlines

    def _parse_run(self, run: ET.Element, xpath: str) -> list[InlineNode]:
        """Convert a <w:r> element to one or more InlineNodes."""
        rpr = run.find(_tag("w", "rPr"))
        bold = _run_is_bold(rpr)
        italic = _run_is_italic(rpr)
        underline = _run_is_underline(rpr)
        strike = _run_is_strike(rpr)
        code = _run_is_code(rpr)
        sup = _run_is_super(rpr)
        sub = _run_is_sub(rpr)

        nodes: list[InlineNode] = []
        child_counts: dict[str, int] = {}

        for child in run:
            tag = child.tag
            child_counts[tag] = child_counts.get(tag, 0) + 1
            ci = child_counts[tag]
            local = self._clark_to_prefix(tag)
            child_xpath = f"{xpath}/{local}[{ci}]"

            if tag == _tag("w", "t"):
                text = child.text or ""
                if text:
                    nodes.append(
                        TextRun(
                            text=text,
                            xpath=child_xpath,
                            bold=bold,
                            italic=italic,
                            underline=underline,
                            strikethrough=strike,
                            code=code,
                            superscript=sup,
                            subscript=sub,
                        )
                    )
            elif tag == _tag("w", "br"):
                br_type = child.get(_tag("w", "type"), "")
                if br_type == "textWrapping":
                    nodes.append(LineBreak(xpath=child_xpath))
                elif br_type == "page":
                    nodes.append(SoftBreak(xpath=child_xpath))
                else:
                    nodes.append(SoftBreak(xpath=child_xpath))
            elif tag == _tag("w", "drawing"):
                img = self._parse_drawing(child, child_xpath)
                if img is not None:
                    nodes.append(img)
            elif tag == _tag("w", "tab"):
                nodes.append(TextRun(text="\t", xpath=child_xpath, bold=bold, italic=italic))

        return nodes

    def _parse_hyperlink(self, el: ET.Element, xpath: str) -> Link:
        """Convert <w:hyperlink> to a Link node."""
        rid = el.get(_tag("r", "id"), "")
        href = self._rels.get(rid, "")
        if not href:
            # Inline anchor
            href = "#" + el.get(_tag("w", "anchor"), "")

        children: list[InlineNode] = []
        run_counts: dict[str, int] = {}
        for child in el:
            if child.tag == _tag("w", "r"):
                run_counts[child.tag] = run_counts.get(child.tag, 0) + 1
                idx = run_counts[child.tag]
                run_xpath = f"{xpath}/w:r[{idx}]"
                children.extend(self._parse_run(child, run_xpath))

        return Link(href=href, children=children, xpath=xpath)

    def _parse_drawing(self, el: ET.Element, xpath: str) -> Optional[Image]:
        """Extract image info from <w:drawing>."""
        # Look for blip (image reference)
        blip = el.find(f".//{_tag('a','blip')}")
        rid = ""
        if blip is not None:
            # a:blip r:embed="rIdX"
            r_ns = NS["r"]
            rid = blip.get(f"{{{r_ns}}}embed", "")

        src = self._rels.get(rid, rid)
        # Try to get alt text
        docpr = el.find(f".//{_tag('wp','docPr')}")
        alt = ""
        if docpr is not None:
            alt = docpr.get("descr", docpr.get("name", ""))

        return Image(alt=alt, src=src, xpath=xpath)

    # ------------------------------------------------------------------
    # Table parsing
    # ------------------------------------------------------------------

    def _parse_table(self, tbl: ET.Element, xpath: str) -> Table:
        rows: list[TableRow] = []
        tr_idx = 0
        for child in tbl:
            if child.tag == _tag("w", "tr"):
                tr_idx += 1
                row_xpath = f"{xpath}/w:tr[{tr_idx}]"
                rows.append(self._parse_table_row(child, row_xpath, tr_idx == 1))
        return Table(rows=rows, xpath=xpath)

    def _parse_table_row(
        self, tr: ET.Element, xpath: str, is_first_row: bool
    ) -> TableRow:
        cells: list[TableCell] = []
        tc_idx = 0
        for child in tr:
            if child.tag == _tag("w", "tc"):
                tc_idx += 1
                cell_xpath = f"{xpath}/w:tc[{tc_idx}]"
                cells.append(self._parse_table_cell(child, cell_xpath, is_first_row))
        is_header = is_first_row
        return TableRow(cells=cells, xpath=xpath, is_header=is_header)

    def _parse_table_cell(
        self, tc: ET.Element, xpath: str, is_header_row: bool
    ) -> TableCell:
        children: list[BlockNode] = []
        raw = self._collect_raw_blocks(tc, xpath)
        children = self._group_lists(raw)

        # Detect grid span (colspan)
        tcpr = tc.find(_tag("w", "tcPr"))
        colspan = 1
        if tcpr is not None:
            gspan = tcpr.find(_tag("w", "gridSpan"))
            if gspan is not None:
                colspan = int(gspan.get(_tag("w", "val"), "1"))

        return TableCell(
            children=children,
            xpath=xpath,
            colspan=colspan,
            is_header=is_header_row,
        )

    # ------------------------------------------------------------------
    # List grouping
    # ------------------------------------------------------------------

    def _group_lists(self, blocks: list[BlockNode]) -> list[BlockNode]:
        """Group consecutive _ListParagraph nodes into BulletList / OrderedList."""
        result: list[BlockNode] = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            if isinstance(block, _ListParagraph):
                # Collect a run of list paragraphs
                group: list[_ListParagraph] = []
                while i < len(blocks) and isinstance(blocks[i], _ListParagraph):
                    group.append(blocks[i])  # type: ignore[arg-type]
                    i += 1
                result.extend(self._build_list_nodes(group))
            else:
                result.append(block)
                i += 1
        return result

    def _build_list_nodes(
        self, group: list[_ListParagraph]
    ) -> list[BlockNode]:
        """Convert a flat list of _ListParagraph items into nested list nodes.

        Simple single-level approach: each item becomes a ListItem whose
        single child is a Paragraph.  Nested depth is tracked but not
        recursively nested for simplicity in this experimental version.
        """
        if not group:
            return []

        # Determine whether the top-level list is ordered
        first = group[0]
        is_ordered = first.is_ordered
        start_val = first.start_val

        items: list[ListItem] = []
        for lp in group:
            para = Paragraph(children=lp.inlines, xpath=lp.xpath, style_id=lp.style_id)
            items.append(ListItem(children=[para], xpath=lp.xpath, depth=lp.ilvl))

        if is_ordered:
            return [OrderedList(items=items, start=start_val, xpath=group[0].xpath)]
        else:
            return [BulletList(items=items, xpath=group[0].xpath)]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _clark_to_prefix(self, clark_tag: str) -> str:
        """Convert Clark-notation tag to prefix:local for use in XPath strings."""
        for prefix, uri in NS.items():
            uri_braced = f"{{{uri}}}"
            if clark_tag.startswith(uri_braced):
                return f"{prefix}:{clark_tag[len(uri_braced):]}"
        return clark_tag


# ---------------------------------------------------------------------------
# Internal-only dataclass for list detection (not part of public AST)
# ---------------------------------------------------------------------------


@dataclass
class _ListParagraph:
    """Intermediate node used during list grouping — never appears in the final AST."""

    inlines: list[InlineNode]
    xpath: str
    style_id: str
    num_id: str
    ilvl: int
    is_ordered: bool
    start_val: int = 1

    def to_dict(self) -> dict:  # pragma: no cover
        raise NotImplementedError("_ListParagraph is internal only")
