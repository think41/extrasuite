"""
Apply DiffOp operations back to a DOCX file.

Reads the DOCX, manipulates word/document.xml using the xpath references
carried by each op, then writes the modified DOCX to a new path.

Supported operations:
  ReplaceParagraph  — update inline content of a paragraph
  ReplaceHeading    — update style + inline content of a heading
  ReplaceCodeBlock  — update text content of a code block paragraph
  DeleteBlock       — remove a w:p or w:tbl element
  InsertBlock       — insert a new w:p (or list of w:p) after a reference element
  ReplaceTable      — update table cell text content
  ReplaceList       — apply per-item ops (insert/delete/replace) to list paragraphs
  ReplaceBlockQuote — recursively apply inner ops to block-quote paragraphs

Public API:
    apply_ops(
        docx_path:     Path | str,
        ops:           list[DiffOp],
        output_path:   Path | str,
        base_children: list[BlockNode] | None = None,
    ) -> None
"""

from __future__ import annotations

import copy
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Union

from extradocx.ast_nodes import (
    BlockNode,
    BlockQuote,
    BulletList,
    CodeBlock,
    Heading,
    Image,
    InlineNode,
    LineBreak,
    Link,
    ListItem,
    OrderedList,
    Paragraph,
    Table,
    TextRun,
    ThematicBreak,
)
from extradocx.diff_ops import (
    DeleteBlock,
    DeleteListItem,
    DiffOp,
    InsertBlock,
    InsertListItem,
    ReplaceBlockQuote,
    ReplaceCodeBlock,
    ReplaceHeading,
    ReplaceList,
    ReplaceListItem,
    ReplaceParagraph,
    ReplaceTable,
)

# ---------------------------------------------------------------------------
# XML namespace constants
# ---------------------------------------------------------------------------

_W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_URI = "http://www.w3.org/XML/1998/namespace"
W = f"{{{_W_URI}}}"
XML = f"{{{_XML_URI}}}"

_NS = {
    "w": _W_URI,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "xml": _XML_URI,
}

# Register namespaces so ElementTree round-trips them correctly.
for _pfx, _uri in _NS.items():
    ET.register_namespace(_pfx, _uri)
ET.register_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
ET.register_namespace("wpc", "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas")
ET.register_namespace("ct", "http://schemas.openxmlformats.org/package/2006/content-types")
ET.register_namespace("dcterms", "http://purl.org/dc/terms/")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
ET.register_namespace(
    "cp", "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
ET.register_namespace(
    "ep",
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_ops(
    docx_path: Union[Path, str],
    ops: list[DiffOp],
    output_path: Union[Path, str],
    base_children: list[BlockNode] | None = None,
) -> None:
    """Apply *ops* to the DOCX at *docx_path*, writing the result to *output_path*.

    Parameters
    ----------
    docx_path:
        Source .docx file.
    ops:
        List of DiffOp from ``md_diff.diff()``.
    output_path:
        Destination .docx file (can equal docx_path for in-place edit).
    base_children:
        Optional list of BlockNodes from the base Document (used only for
        logging / future diagnostics; not required for correctness).
    """
    docx_path = Path(docx_path)
    output_path = Path(output_path)

    # Read all files from the zip
    with zipfile.ZipFile(docx_path, "r") as zf:
        file_map: dict[str, bytes] = {name: zf.read(name) for name in zf.namelist()}
        zip_info_map: dict[str, zipfile.ZipInfo] = {info.filename: info for info in zf.infolist()}

    doc_xml = file_map.get("word/document.xml", b"")
    if not doc_xml:
        raise ValueError("No word/document.xml found in the DOCX archive")

    # Parse XML — preserve namespace declarations via ET.register_namespace above
    root = ET.fromstring(doc_xml)

    # Find body element for use in InsertBlock
    body = root.find(f"{W}body")
    if body is None:
        raise ValueError("No w:body element found in word/document.xml")

    # Apply operations in a safe order that prevents index invalidation:
    #
    #  1. Replace ops — modify existing elements in-place.  No structural
    #     changes, so xpath resolution is unaffected.
    #
    #  2. Delete ops in REVERSE base_index order — removing elements from the
    #     end of the document first ensures that the xpaths of earlier elements
    #     (needed by subsequent delete/insert ops) remain valid.
    #
    #  3. Insert ops sorted by their after_xpath w:p index (ASCENDING) — after
    #     all deletes are done the tree is stable.  Inserts that reference
    #     higher positions come last; since we use per-tag xpath counting,
    #     inserting at a high index doesn't affect resolution of lower anchors.
    def _para_index_from_xpath(xpath: str) -> int:
        """Extract the numeric index from the last path segment, e.g. w:p[5] → 5."""
        if not xpath:
            return 0
        m = re.search(r"\[(\d+)\]$", xpath)
        return int(m.group(1)) if m else 0

    replaces = [op for op in ops if not isinstance(op, (InsertBlock, DeleteBlock))]
    inserts = sorted(
        [op for op in ops if isinstance(op, InsertBlock)],
        key=lambda op: _para_index_from_xpath(op.after_xpath),
    )
    deletes = sorted(
        [op for op in ops if isinstance(op, DeleteBlock)],
        key=lambda op: op.base_index,
        reverse=True,
    )

    for op in replaces:
        _apply_op(root, body, op)
    for op in deletes:
        _apply_op(root, body, op)
    for op in inserts:
        _apply_op(root, body, op)

    # Serialise back to bytes
    new_doc_xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
    # Prepend XML declaration (ET strips it when encoding='unicode')
    xml_decl = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    new_doc_bytes = (xml_decl + new_doc_xml).encode("utf-8")

    # Write new DOCX
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out_zf:
        for name, data in file_map.items():
            info = zip_info_map[name]
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = zipfile.ZIP_DEFLATED
            if name == "word/document.xml":
                out_zf.writestr(new_info, new_doc_bytes)
            else:
                out_zf.writestr(new_info, data)

    output_path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# Operation dispatch
# ---------------------------------------------------------------------------


def _apply_op(root: ET.Element, body: ET.Element, op: DiffOp) -> None:
    """Dispatch a single DiffOp to the appropriate handler."""
    if isinstance(op, ReplaceParagraph):
        _apply_replace_paragraph(root, op)
    elif isinstance(op, ReplaceHeading):
        _apply_replace_heading(root, op)
    elif isinstance(op, ReplaceCodeBlock):
        _apply_replace_codeblock(root, op)
    elif isinstance(op, DeleteBlock):
        _apply_delete_block(root, op)
    elif isinstance(op, InsertBlock):
        _apply_insert_block(root, body, op)
    elif isinstance(op, ReplaceTable):
        _apply_replace_table(root, op)
    elif isinstance(op, ReplaceList):
        _apply_replace_list(root, op)
    elif isinstance(op, ReplaceBlockQuote):
        _apply_replace_blockquote(root, op)
    # Other op types silently ignored for now


# ---------------------------------------------------------------------------
# XPath resolution
# ---------------------------------------------------------------------------

_XPATH_PART_RE = re.compile(r"(\w+):(\w+)\[(\d+)\]")


def _find_by_xpath(root: ET.Element, xpath: str) -> ET.Element | None:
    """Resolve a /w:document[1]/... XPath from the document root element.

    The xpath uses per-tag counting: w:p[3] means the 3rd <w:p> child,
    not the 3rd child overall.
    """
    if not xpath:
        return None
    parts = xpath.strip("/").split("/")
    current = root
    for part in parts[1:]:  # parts[0] is 'w:document[1]' — root itself
        m = _XPATH_PART_RE.match(part)
        if not m:
            return None
        prefix, local, idx = m.group(1), m.group(2), int(m.group(3))
        uri = _NS.get(prefix, "")
        tag = f"{{{uri}}}{local}"
        count = 0
        found = None
        for child in current:
            if child.tag == tag:
                count += 1
                if count == idx:
                    found = child
                    break
        if found is None:
            return None
        current = found
    return current


def _find_parent(root: ET.Element, target: ET.Element) -> ET.Element | None:
    """Walk the tree to find the parent of *target*."""
    for parent in root.iter():
        if target in list(parent):
            return parent
    return None


def _body_child_index(body: ET.Element, element: ET.Element) -> int:
    """Return the index of *element* among direct children of *body*."""
    children = list(body)
    for i, child in enumerate(children):
        if child is element:
            return i
    return -1


# ---------------------------------------------------------------------------
# Paragraph / heading content replacement
# ---------------------------------------------------------------------------


def _apply_replace_paragraph(root: ET.Element, op: ReplaceParagraph) -> None:
    para = _find_by_xpath(root, op.base_xpath)
    if para is None:
        return
    _replace_inline_content(para, op.new_children)


def _apply_replace_heading(root: ET.Element, op: ReplaceHeading) -> None:
    para = _find_by_xpath(root, op.base_xpath)
    if para is None:
        return

    # Update style if level changed
    if op.old_level != op.new_level and op.new_level > 0:
        new_style_id = f"Heading{op.new_level}"
        _set_para_style(para, new_style_id)

    _replace_inline_content(para, op.new_children)


def _apply_replace_codeblock(root: ET.Element, op: ReplaceCodeBlock) -> None:
    para = _find_by_xpath(root, op.base_xpath)
    if para is None:
        return
    # Replace the text content, keeping the existing code style
    _replace_inline_content(para, [TextRun(text=op.new_code, xpath="")])


def _set_para_style(para: ET.Element, style_id: str) -> None:
    """Set or update the paragraph style in w:pPr/w:pStyle."""
    ppr = para.find(f"{W}pPr")
    if ppr is None:
        ppr = ET.Element(f"{W}pPr")
        para.insert(0, ppr)

    pstyle = ppr.find(f"{W}pStyle")
    if pstyle is None:
        pstyle = ET.SubElement(ppr, f"{W}pStyle")
        # Insert at position 0 in pPr (pStyle must be first)
        ppr.remove(pstyle)
        ppr.insert(0, pstyle)

    pstyle.set(f"{W}val", style_id)


def _replace_inline_content(para: ET.Element, inlines: list[InlineNode]) -> None:
    """Remove all run-type children of *para* and replace with *inlines*."""
    # Remove existing runs, hyperlinks (but preserve w:pPr)
    to_remove = []
    for child in para:
        tag = child.tag
        if tag in (
            f"{W}r",
            f"{W}hyperlink",
            f"{W}ins",
            f"{W}del",
            f"{W}bookmarkStart",
            f"{W}bookmarkEnd",
        ):
            to_remove.append(child)

    for child in to_remove:
        para.remove(child)

    # Add new runs
    new_runs = _inlines_to_xml(inlines)
    for run_el in new_runs:
        para.append(run_el)


# ---------------------------------------------------------------------------
# Delete block
# ---------------------------------------------------------------------------


def _apply_delete_block(root: ET.Element, op: DeleteBlock) -> None:
    if not op.base_xpath:
        return
    target = _find_by_xpath(root, op.base_xpath)
    if target is None:
        return
    parent = _find_parent(root, target)
    if parent is None:
        return
    parent.remove(target)


# ---------------------------------------------------------------------------
# Insert block
# ---------------------------------------------------------------------------


def _apply_insert_block(root: ET.Element, body: ET.Element, op: InsertBlock) -> None:
    """Insert new XML elements for *op.block* after the element at *op.after_xpath*.

    If after_xpath is empty, insert at the beginning of body (before first child).
    """
    new_elements = _block_to_xml_elements(op.block)
    if not new_elements:
        return

    if op.after_xpath:
        after_el = _find_by_xpath(root, op.after_xpath)
        if after_el is None:
            # Fallback: append to body before sectPr
            _insert_before_sectpr(body, new_elements)
            return
        parent = _find_parent(root, after_el)
        if parent is None:
            _insert_before_sectpr(body, new_elements)
            return
        # Insert each new element after after_el
        ref_idx = _body_child_index(parent, after_el)
        if ref_idx == -1:
            _insert_before_sectpr(body, new_elements)
            return
        for i, el in enumerate(new_elements):
            parent.insert(ref_idx + 1 + i, el)
    else:
        # Insert at beginning of body
        for i, el in enumerate(new_elements):
            body.insert(i, el)


def _insert_before_sectpr(body: ET.Element, elements: list[ET.Element]) -> None:
    """Append elements to body, just before the last w:sectPr if present."""
    children = list(body)
    insert_idx = len(children)
    # Find sectPr (section properties — last child of body, must stay last)
    for i in reversed(range(len(children))):
        if children[i].tag == f"{W}sectPr":
            insert_idx = i
            break
    for i, el in enumerate(elements):
        body.insert(insert_idx + i, el)


# ---------------------------------------------------------------------------
# Replace table
# ---------------------------------------------------------------------------


def _apply_replace_table(root: ET.Element, op: ReplaceTable) -> None:
    tbl = _find_by_xpath(root, op.base_xpath)
    if tbl is None:
        return

    # Collect existing table rows
    existing_rows = [child for child in tbl if child.tag == f"{W}tr"]

    # Iterate over the new rows and update cell content
    for ri, new_row in enumerate(op.new_rows):
        if ri >= len(existing_rows):
            break  # Don't add new rows for now — just update existing
        existing_tr = existing_rows[ri]
        existing_cells = [child for child in existing_tr if child.tag == f"{W}tc"]
        for ci, new_cell in enumerate(new_row.cells):
            if ci >= len(existing_cells):
                break
            existing_tc = existing_cells[ci]
            # Get the first paragraph in the cell
            cell_paras = [child for child in existing_tc if child.tag == f"{W}p"]
            if cell_paras:
                new_inlines: list[InlineNode] = []
                for child_block in new_cell.children:
                    if isinstance(child_block, Paragraph):
                        new_inlines.extend(child_block.children)
                    elif isinstance(child_block, Heading):
                        new_inlines.extend(child_block.children)
                _replace_inline_content(cell_paras[0], new_inlines)


# ---------------------------------------------------------------------------
# Replace list
# ---------------------------------------------------------------------------


def _apply_replace_list(root: ET.Element, op: ReplaceList) -> None:
    """Apply per-item ops within a list.

    List items in DOCX are individual w:p elements, each carrying a numPr.
    The base_xpath on each list item op points to the specific w:p.
    """
    for item_op in op.item_ops:
        if isinstance(item_op, ReplaceListItem):
            para = _find_by_xpath(root, item_op.base_xpath)
            if para is None:
                continue
            inlines = [TextRun(text=item_op.new_text, xpath="")]
            _replace_inline_content(para, inlines)

        elif isinstance(item_op, DeleteListItem):
            if not item_op.base_xpath:
                continue
            target = _find_by_xpath(root, item_op.base_xpath)
            if target is None:
                continue
            parent = _find_parent(root, target)
            if parent is not None:
                parent.remove(target)

        elif isinstance(item_op, InsertListItem):
            # Find the list item at the position before this insertion
            # and copy its structure (to preserve numPr), then update text
            item = item_op.item
            if not isinstance(item, ListItem):
                continue
            # Use the list's base_xpath to find sibling paragraphs and
            # copy the last one to inherit numbering properties
            _insert_list_item(root, op.base_xpath, item)


def _insert_list_item(
    root: ET.Element,
    list_xpath: str,
    new_item: ListItem,
) -> None:
    """Insert a new list item w:p by cloning a sibling's structure."""
    # Find a reference paragraph in the list to clone numbering from
    list_el = _find_by_xpath(root, list_xpath)
    if list_el is None:
        return
    parent = _find_parent(root, list_el)
    if parent is None:
        return

    # Clone the reference element, update its text
    template = copy.deepcopy(list_el)
    # Replace text content in the clone
    item_text = " ".join(
        run.text
        for child_block in new_item.children
        for run in (child_block.children if isinstance(child_block, Paragraph) else [])
        if isinstance(run, TextRun)
    )
    _replace_inline_content(template, [TextRun(text=item_text, xpath="")])

    # Insert the clone after the reference
    ref_idx = _body_child_index(parent, list_el)
    if ref_idx >= 0:
        parent.insert(ref_idx + 1, template)


# ---------------------------------------------------------------------------
# Replace block quote
# ---------------------------------------------------------------------------


def _apply_replace_blockquote(root: ET.Element, op: ReplaceBlockQuote) -> None:
    """Apply inner ops to the contents of a block quote."""
    body = root.find(f"{W}body")
    if body is None:
        return
    for inner_op in op.inner_ops:
        _apply_op(root, body, inner_op)


# ---------------------------------------------------------------------------
# XML element creation helpers
# ---------------------------------------------------------------------------


def _block_to_xml_elements(block: BlockNode) -> list[ET.Element]:
    """Convert an AST block node to one or more w:p / w:tbl elements."""
    if isinstance(block, Paragraph):
        return [_make_para_element(block.children, style_id="")]
    elif isinstance(block, Heading):
        style_id = f"Heading{block.level}"
        return [_make_para_element(block.children, style_id=style_id)]
    elif isinstance(block, CodeBlock):
        return [_make_code_para_element(block)]
    elif isinstance(block, ThematicBreak):
        # A horizontal rule — insert an empty paragraph with "HR" style
        return [_make_para_element([], style_id="")]
    elif isinstance(block, BulletList):
        return _make_list_elements(block.items, ordered=False)
    elif isinstance(block, OrderedList):
        return _make_list_elements(block.items, ordered=True)
    elif isinstance(block, Table):
        # For now skip table insertion (complex)
        return []
    elif isinstance(block, BlockQuote):
        return [
            _make_para_element(
                inner.children if isinstance(inner, Paragraph) else [], style_id="Quote"
            )
            for inner in block.children
            if isinstance(inner, Paragraph)
        ]
    return []


def _make_para_element(inlines: list[InlineNode], style_id: str) -> ET.Element:
    """Create a <w:p> element with the given inline content and style."""
    para = ET.Element(f"{W}p")

    if style_id:
        ppr = ET.SubElement(para, f"{W}pPr")
        pstyle = ET.SubElement(ppr, f"{W}pStyle")
        pstyle.set(f"{W}val", style_id)

    for run_el in _inlines_to_xml(inlines):
        para.append(run_el)

    return para


def _make_code_para_element(block: CodeBlock) -> ET.Element:
    """Create a <w:p> element for a code block with monospace font."""
    para = ET.Element(f"{W}p")

    ppr = ET.SubElement(para, f"{W}pPr")
    pstyle = ET.SubElement(ppr, f"{W}pStyle")
    pstyle.set(f"{W}val", "Code")

    for line in block.code.split("\n"):
        run = ET.SubElement(para, f"{W}r")
        rpr = ET.SubElement(run, f"{W}rPr")
        fonts = ET.SubElement(rpr, f"{W}rFonts")
        fonts.set(f"{W}ascii", "Courier New")
        fonts.set(f"{W}hAnsi", "Courier New")
        t = ET.SubElement(run, f"{W}t")
        t.text = line
        if line and (line[0] == " " or line[-1] == " "):
            t.set(f"{XML}space", "preserve")

    return para


def _make_list_elements(items: list[ListItem], *, ordered: bool) -> list[ET.Element]:
    """Create w:p elements for each list item with a minimal numPr stub."""
    elements: list[ET.Element] = []
    style_id = "ListNumber" if ordered else "ListBullet"
    for item in items:
        inlines: list[InlineNode] = []
        for child in item.children:
            if isinstance(child, Paragraph):
                inlines.extend(child.children)
        para = ET.Element(f"{W}p")
        ppr = ET.SubElement(para, f"{W}pPr")
        pstyle = ET.SubElement(ppr, f"{W}pStyle")
        pstyle.set(f"{W}val", style_id)
        for run_el in _inlines_to_xml(inlines):
            para.append(run_el)
        elements.append(para)
    return elements


def _inlines_to_xml(inlines: list[InlineNode]) -> list[ET.Element]:
    """Convert inline AST nodes to a list of w:r / w:hyperlink elements."""
    result: list[ET.Element] = []
    for node in inlines:
        if isinstance(node, TextRun):
            result.append(_make_run_element(node))
        elif isinstance(node, Link):
            # Render link as plain text run (can't create rels easily)
            link_text = ""
            for child in node.children:
                if isinstance(child, TextRun):
                    link_text += child.text
            if link_text:
                result.append(_make_run_element(TextRun(text=link_text, xpath="")))
        elif isinstance(node, Image):
            # Skip images — can't recreate from markdown
            pass
        elif isinstance(node, LineBreak):
            run = ET.Element(f"{W}r")
            br = ET.SubElement(run, f"{W}br")
            br.set(f"{W}type", "textWrapping")
            result.append(run)
    return result


def _make_run_element(run: TextRun) -> ET.Element:
    """Convert a TextRun AST node to a <w:r> XML element."""
    r = ET.Element(f"{W}r")

    # Build rPr only if there are formatting flags
    if run.bold or run.italic or run.underline or run.strikethrough or run.code:
        rpr = ET.SubElement(r, f"{W}rPr")
        if run.bold:
            ET.SubElement(rpr, f"{W}b")
        if run.italic:
            ET.SubElement(rpr, f"{W}i")
        if run.underline:
            u = ET.SubElement(rpr, f"{W}u")
            u.set(f"{W}val", "single")
        if run.strikethrough:
            ET.SubElement(rpr, f"{W}strike")
        if run.code:
            fonts = ET.SubElement(rpr, f"{W}rFonts")
            fonts.set(f"{W}ascii", "Courier New")
            fonts.set(f"{W}hAnsi", "Courier New")

    t = ET.SubElement(r, f"{W}t")
    t.text = run.text
    # xml:space="preserve" is needed when text starts/ends with whitespace
    if run.text and (run.text[0] == " " or run.text[-1] == " "):
        t.set(f"{XML}space", "preserve")

    return r
