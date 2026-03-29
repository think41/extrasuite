"""Document → markdown serialization.

Converts Google Docs Document API objects to markdown text.
Each tab becomes a 'document.md' file in its folder.

Supported:
  - Headings h1-h6 (HEADING_1-6, TITLE→#, SUBTITLE→##)
  - Normal paragraphs
  - Bold (**text**), italic (*text*), strikethrough (~~text~~), underline (<u>text</u>)
  - Hyperlinks [text](url)
  - Bullet (-), numbered (1.), checkbox (- [ ]) lists with nesting
  - GFM pipe tables (simple) or HTML <table> (styled / colspan / rowspan)
  - Horizontal rules (---)
  - Page breaks (<x-pagebreak/>)
  - Passthrough inline elements: <x-img>, <x-person>, <x-fn>, <x-chip>,
    <x-br/>, <x-colbreak/>, <x-date/>, <x-auto/>, <x-eq/>
  - Fenced code blocks via extradoc:codeblock named range → ```lang\\ncode\\n```
  - Callouts via extradoc:callout:* named range → > [!TYPE]\\n> text
  - Blockquotes via extradoc:blockquote named range → > text
  - Inline code (Courier New text run) → `code`
"""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING, Any

from extradoc.serde._special_elements import special_element_from_named_range
from extradoc.serde._utils import (
    _style_has_attrs,
    optional_color_to_hex,
    sanitize_tab_name,
    serialize_text_run,
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Document,
        DocumentTab,
        Paragraph,
        ParagraphElement,
        StructuralElement,
        Table,
    )

# Named style → heading prefix (TITLE/SUBTITLE are lossy on round-trip)
_STYLE_TO_HEADING: dict[str, str] = {
    "HEADING_1": "#",
    "HEADING_2": "##",
    "HEADING_3": "###",
    "HEADING_4": "####",
    "HEADING_5": "#####",
    "HEADING_6": "######",
    "TITLE": "#",
    "SUBTITLE": "##",
}


def document_to_markdown(doc: Document) -> dict[str, dict[str, str]]:
    """Convert a Document to per-tab markdown content.

    Returns:
        dict[folder_name → dict[filename → content]]
        Each tab produces at minimum {"document.md": "..."}.
    """
    result: dict[str, dict[str, str]] = {}
    for tab in doc.tabs or []:
        props = tab.tab_properties
        tab_title = (props.title or "Tab 1") if props else "Tab 1"
        folder = sanitize_tab_name(tab_title)

        dt = tab.document_tab
        if not dt:
            result[folder] = {"document.md": ""}
            continue

        list_defs = dt.lists or {}
        content = _serialize_body(dt, list_defs)
        result[folder] = {"document.md": content}

    return result


# ---------------------------------------------------------------------------
# Body serialization
# ---------------------------------------------------------------------------


def _build_named_range_index(doc_tab: DocumentTab) -> list[tuple[int, int, str]]:
    """Build a sorted [(si, ei, name)] list from the tab's extradoc:* named ranges.

    Iterates ALL NamedRange objects within each name group, so multiple ranges
    with the same name (e.g. two callout:warning blocks) are both indexed.

    Returns a list sorted by si so that _find_annotation can do a quick scan.
    """
    spans: list[tuple[int, int, str]] = []
    for name, group in (doc_tab.named_ranges or {}).items():
        if not name.startswith("extradoc:"):
            continue
        for nr in (group.named_ranges or []):
            for r in (nr.ranges or []):
                si = r.start_index
                ei = r.end_index
                if si is not None and ei is not None:
                    spans.append((si, ei, name))
    spans.sort(key=lambda t: t[0])
    return spans


def _find_annotation(
    nr_spans: list[tuple[int, int, str]], table_si: int
) -> str | None:
    """Return the extradoc:* name whose span contains table_si, or None.

    The real Google Docs API may assign table startIndex values that drift by a
    small amount from the named range we previously wrote. In live docs we have
    observed the table start index land one code point before the named-range
    start, so accept a small lead-in window as long as the table start is still
    immediately adjacent to the range.
    """
    matches: list[tuple[int, int, str]] = []
    for si, ei, name in nr_spans:
        if (si <= table_si < ei) or (table_si + 1 == si and table_si < ei):
            distance = abs(table_si - si)
            span_width = ei - si
            matches.append((distance, span_width, name))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return matches[0][2]


def _serialize_body(doc_tab: DocumentTab, list_defs: dict[str, Any]) -> str:
    list_types = {lid: _detect_list_type(ld) for lid, ld in list_defs.items()}
    nr_spans = _build_named_range_index(doc_tab)

    # Collect footnote text from footnote segments
    footnote_defs: dict[str, str] = {}
    for fn_id, fn in (doc_tab.footnotes or {}).items():
        parts: list[str] = []
        for se in fn.content or []:
            if se.paragraph:
                parts.append(_serialize_inlines(se.paragraph.elements or []))
        footnote_defs[fn_id] = " ".join(p for p in parts if p)

    body_content = doc_tab.body.content if doc_tab.body else []
    blocks = _serialize_content(body_content, list_types, nr_spans)

    # Append footnote definitions
    if footnote_defs:
        blocks.append("")
        for fn_id, fn_text in footnote_defs.items():
            blocks.append(f"[^{fn_id}]: {fn_text}")

    return "\n".join(blocks) + "\n"


def _serialize_content(
    content: list[StructuralElement],
    list_types: dict[str, str],
    nr_spans: list[tuple[int, int, str]] | None = None,
) -> list[str]:
    """Serialize a list of StructuralElements to markdown lines."""
    lines: list[str] = []
    in_list = False
    current_list_id: str | None = None
    spans = nr_spans or []

    for se in content:
        if se.section_break is not None:
            continue

        if se.table_of_contents is not None:
            if in_list:
                in_list = False
                current_list_id = None
            if lines:
                lines.append("")
            lines.append("<!-- toc -->")
            continue

        if se.table is not None:
            if in_list:
                in_list = False
                current_list_id = None
            if lines:
                lines.append("")
            # Check for extradoc:* named range annotation via containment check
            annotation = _find_annotation(spans, se.start_index or 0)
            if annotation:
                elem = special_element_from_named_range(se.table, annotation)
                lines.append(elem.to_markdown())
            else:
                lines.append(_serialize_table(se.table))
            continue

        if se.paragraph is not None:
            para = se.paragraph

            if _is_colored_empty_paragraph(para):
                # Cannot represent color styling in markdown, but emit a
                # placeholder so the reconciler does not delete the paragraph.
                if lines:
                    lines.append("")
                lines.append("<!-- -->")
                continue

            if _is_trailing_paragraph(para):
                continue

            # Horizontal rule / page break paragraphs
            for pe in para.elements or []:
                if pe.horizontal_rule is not None:
                    if in_list:
                        in_list = False
                        current_list_id = None
                    if lines:
                        lines.append("")
                    lines.append("---")
                    break
                if pe.page_break is not None:
                    if in_list:
                        in_list = False
                        current_list_id = None
                    if lines:
                        lines.append("")
                    lines.append("<x-pagebreak/>")
                    break
            else:
                bullet = para.bullet
                if bullet:
                    line = _serialize_list_item(para, list_types)
                    if line is not None:
                        this_list_id = bullet.list_id
                        if lines and (not in_list or this_list_id != current_list_id):
                            lines.append("")
                        lines.append(line)
                        in_list = True
                        current_list_id = this_list_id
                    continue
                else:
                    if in_list:
                        in_list = False
                        current_list_id = None
                    block = _serialize_paragraph(para)
                    if block is not None:
                        if lines:
                            lines.append("")
                        lines.append(block)

    return lines


def _is_trailing_paragraph(para: Paragraph) -> bool:
    elements = para.elements or []
    if not elements:
        return True
    if len(elements) == 1:
        tr = elements[0].text_run
        if tr is not None and tr.content == "\n":
            ts = tr.text_style
            return ts is None or not _style_has_attrs(ts)
    return False


def _is_colored_empty_paragraph(para: Paragraph) -> bool:
    """Return True for empty paragraphs whose only styling is foreground/background color.

    These cannot be represented in markdown but should not be silently deleted
    on push.  They are emitted as <!-- --> placeholders so that the round-trip
    preserves paragraph count and the reconciler does not generate spurious
    deleteContentRange requests.
    """
    elements = para.elements or []
    if len(elements) != 1:
        return False
    tr = elements[0].text_run
    if tr is None or tr.content != "\n":
        return False
    ts = tr.text_style
    if ts is None:
        return False
    # Must have some style set, but none that _style_has_attrs covers.
    return not _style_has_attrs(ts) and (
        ts.foreground_color is not None or ts.background_color is not None
    )


def _serialize_paragraph(para: Paragraph) -> str | None:
    inline = _serialize_inlines(para.elements or [])
    if not inline.strip():
        return None

    ps = para.paragraph_style
    named_style = ps.named_style_type.value if ps and ps.named_style_type else None
    prefix = _STYLE_TO_HEADING.get(named_style or "")
    if prefix:
        return f"{prefix} {inline}"
    return inline


def _serialize_list_item(para: Paragraph, list_types: dict[str, str]) -> str | None:
    bullet = para.bullet
    if not bullet:
        return None

    inline = _serialize_inlines(para.elements or [])
    nesting = bullet.nesting_level or 0
    list_type = list_types.get(bullet.list_id or "", "bullet")
    indent = "  " * nesting

    if list_type == "decimal":
        return f"{indent}1. {inline}"
    elif list_type == "checkbox":
        return f"{indent}- [ ] {inline}"
    else:
        return f"{indent}- {inline}"


# ---------------------------------------------------------------------------
# Inline serialization
# ---------------------------------------------------------------------------


def _serialize_inlines(elements: list[ParagraphElement]) -> str:
    return "".join(_serialize_inline_elem(pe) for pe in elements)


def _serialize_inline_elem(pe: ParagraphElement) -> str:
    if pe.text_run is not None:
        return _serialize_text_run(pe.text_run)

    if pe.inline_object_element is not None:
        obj_id = pe.inline_object_element.inline_object_id or ""
        return f'<x-img id="{obj_id}"/>'

    if pe.footnote_reference is not None:
        fn_id = pe.footnote_reference.footnote_id or ""
        return f"[^{fn_id}]"

    if pe.person is not None:
        props = pe.person.person_properties
        email = (props.email or "") if props else ""
        name = (props.name or "") if props else ""
        if name:
            return (
                f'<x-person email="{email}" name="{_html.escape(name, quote=True)}"/>'
            )
        return f'<x-person email="{email}"/>'

    if pe.rich_link is not None:
        props = pe.rich_link.rich_link_properties
        url = (props.uri or "") if props else ""
        title = (props.title or "") if props else ""
        if title:
            return f'<x-chip url="{url}" title="{_html.escape(title, quote=True)}"/>'
        return f'<x-chip url="{url}"/>'

    if pe.column_break is not None:
        return "<x-colbreak/>"

    if pe.date_element is not None:
        return "<x-date/>"

    if pe.auto_text is not None:
        return "<x-auto/>"

    if pe.equation is not None:
        return "<x-eq/>"

    return ""


_serialize_text_run = serialize_text_run


# ---------------------------------------------------------------------------
# Table serialization
# ---------------------------------------------------------------------------


def _serialize_table(table: Table) -> str:
    if _needs_html_table(table):
        return _serialize_html_table(table)
    return _serialize_gfm_table(table)


def _needs_html_table(table: Table) -> bool:
    for row in table.table_rows or []:
        for cell in row.table_cells or []:
            s = cell.table_cell_style
            if not s:
                continue
            if (s.column_span and s.column_span > 1) or (s.row_span and s.row_span > 1):
                return True
            if s.background_color and s.background_color.color:
                return True
            if any([s.border_top, s.border_bottom, s.border_left, s.border_right]):
                return True
    return False


def _cell_text(cell: Any) -> str:
    parts: list[str] = []
    for se in cell.content or []:
        if se.paragraph:
            t = _serialize_inlines(se.paragraph.elements or [])
            if t:
                parts.append(t)
    return " ".join(parts).replace("|", "\\|")


def _serialize_gfm_table(table: Table) -> str:
    rows = table.table_rows or []
    if not rows:
        return ""

    cells = [[_cell_text(c) for c in row.table_cells or []] for row in rows]
    n_cols = max((len(r) for r in cells), default=0)
    for row in cells:
        while len(row) < n_cols:
            row.append("")

    header = "| " + " | ".join(cells[0]) + " |"
    sep = "| " + " | ".join("---" for _ in range(n_cols)) + " |"
    data = ["| " + " | ".join(row) + " |" for row in cells[1:]]
    return "\n".join([header, sep, *data])


def _serialize_html_table(table: Table) -> str:
    lines = ["<table>"]
    for i, row in enumerate(table.table_rows or []):
        lines.append("  <tr>")
        tag = "th" if i == 0 else "td"
        for cell in row.table_cells or []:
            attrs = ""
            s = cell.table_cell_style
            if s:
                if s.column_span and s.column_span > 1:
                    attrs += f' colspan="{s.column_span}"'
                if s.row_span and s.row_span > 1:
                    attrs += f' rowspan="{s.row_span}"'
                if s.background_color and s.background_color.color:
                    color = optional_color_to_hex(s.background_color)
                    if color:
                        attrs += f' style="background-color:{color}"'
            text = _cell_text(cell)
            lines.append(f"    <{tag}{attrs}>{text}</{tag}>")
        lines.append("  </tr>")
    lines.append("</table>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# List type detection
# ---------------------------------------------------------------------------


def _detect_list_type(list_def: Any) -> str:
    """Detect bullet/decimal/checkbox from a List definition (Pydantic or dict)."""
    if isinstance(list_def, dict):
        nls = list_def.get("listProperties", {}).get("nestingLevels", [{}])
        lvl = nls[0] if nls else {}
        sym = lvl.get("glyphSymbol", "")
        gtype = lvl.get("glyphType", "")
    else:
        lp = getattr(list_def, "list_properties", None)
        nls = (lp.nesting_levels or []) if lp else []
        first = nls[0] if nls else None
        if first is None:
            return "bullet"

        sym = first.glyph_symbol or ""
        gtype = (
            first.glyph_type.value
            if first.glyph_type and hasattr(first.glyph_type, "value")
            else (first.glyph_type or "")
        )

    if sym == "☐":
        return "checkbox"
    if gtype in ("DECIMAL", "ALPHA", "ROMAN", "UPPER_ALPHA", "UPPER_ROMAN"):
        return "decimal"
    return "bullet"
