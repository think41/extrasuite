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

from .._utils import (
    _style_has_attrs,
    build_heading_maps,
    optional_color_to_hex,
    sanitize_tab_name,
    serialize_text_run,
)
from ._special_elements import special_element_from_named_range

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
        Each document.md starts with YAML frontmatter containing tab id and title.
    """
    heading_id_to_name, _ = build_heading_maps(doc)

    result: dict[str, dict[str, str]] = {}
    for tab in doc.tabs or []:
        props = tab.tab_properties
        tab_title = (props.title or "Tab 1") if props else "Tab 1"
        tab_id = (props.tab_id or "") if props else ""
        folder = sanitize_tab_name(tab_title)

        dt = tab.document_tab
        if not dt:
            frontmatter = f"---\nid: {tab_id}\ntitle: {tab_title}\n---\n\n"
            result[folder] = {"document.md": frontmatter}
            continue

        list_defs = dt.lists or {}
        inline_objs = dt.inline_objects or {}
        content = _serialize_body(dt, list_defs, heading_id_to_name=heading_id_to_name, inline_objects=inline_objs)
        frontmatter = f"---\nid: {tab_id}\ntitle: {tab_title}\n---\n\n"
        result[folder] = {"document.md": frontmatter + content}

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
        for nr in group.named_ranges or []:
            for r in nr.ranges or []:
                si = r.start_index
                ei = r.end_index
                if si is not None and ei is not None:
                    spans.append((si, ei, name))
    spans.sort(key=lambda t: t[0])
    return spans


def _find_annotation(nr_spans: list[tuple[int, int, str]], table_si: int) -> str | None:
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


def _serialize_body(
    doc_tab: DocumentTab,
    list_defs: dict[str, Any],
    *,
    heading_id_to_name: dict[str, str] | None = None,
    inline_objects: dict[str, Any] | None = None,
) -> str:
    h_map = heading_id_to_name or {}
    list_types = {lid: _detect_list_type(ld) for lid, ld in list_defs.items()}
    nr_spans = _build_named_range_index(doc_tab)

    # Collect footnote text from footnote segments
    footnote_defs: dict[str, str] = {}
    for fn_id, fn in (doc_tab.footnotes or {}).items():
        parts: list[str] = []
        for se in fn.content or []:
            if se.paragraph:
                parts.append(_serialize_inlines(se.paragraph.elements or [], heading_id_to_name=h_map, inline_objects=inline_objects))
        footnote_defs[fn_id] = " ".join(p for p in parts if p)

    body_content = (doc_tab.body.content or []) if doc_tab.body else []
    blocks = _serialize_content(body_content, list_types, list_defs, nr_spans, heading_id_to_name=h_map, inline_objects=inline_objects)

    # Append footnote definitions
    if footnote_defs:
        blocks.append("")
        for fn_id, fn_text in footnote_defs.items():
            blocks.append(f"[^{fn_id}]: {fn_text}")

    return "\n".join(blocks) + "\n"


def _serialize_content(
    content: list[StructuralElement],
    list_types: dict[str, str],
    list_defs: dict[str, Any],
    nr_spans: list[tuple[int, int, str]] | None = None,
    *,
    heading_id_to_name: dict[str, str] | None = None,
    inline_objects: dict[str, Any] | None = None,
) -> list[str]:
    """Serialize a list of StructuralElements to markdown lines."""
    lines: list[str] = []
    in_list = False
    current_list_id: str | None = None
    # Nesting level of the most recent list item emitted. Used to indent
    # `<!-- -->` placeholders so they are absorbed as continuation content
    # of the current list item instead of closing the surrounding list.
    current_list_nesting = 0
    # Per-nesting-level counters for ordered (decimal/alpha/roman) lists.
    # Reset when we leave a list or when list_id changes; deeper levels are
    # cleared when we pop back to a shallower level so that re-entering a
    # deeper level restarts numbering at 1.
    list_counters: dict[int, int] = {}
    spans = nr_spans or []
    h_map = heading_id_to_name or {}

    for se in content:
        if se.section_break is not None:
            continue

        if se.table_of_contents is not None:
            if in_list:
                in_list = False
                current_list_id = None
                list_counters = {}
            if lines:
                lines.append("")
            lines.append("<!-- toc -->")
            continue

        if se.table is not None:
            if in_list:
                in_list = False
                current_list_id = None
                list_counters = {}
            if lines:
                lines.append("")
            # Check for extradoc:* named range annotation via containment check
            annotation = _find_annotation(spans, se.start_index or 0)
            if annotation:
                elem = special_element_from_named_range(se.table, annotation)
                lines.append(elem.to_markdown(heading_id_to_name=h_map))
            else:
                lines.append(_serialize_table(se.table, heading_id_to_name=h_map, inline_objects=inline_objects))
            continue

        if se.paragraph is not None:
            para = se.paragraph

            if _is_colored_empty_paragraph(para):
                # Cannot represent color styling in markdown, but emit a
                # placeholder so the reconciler does not delete the paragraph.
                #
                # When we're inside a list, a bare `<!-- -->` at column 0
                # closes the list in CommonMark — the next 4-space-indented
                # sub-item then becomes an indented code block and its
                # content is silently dropped on re-parse. Indent the
                # placeholder one level deeper than the current item's
                # marker so it is absorbed as continuation content instead.
                if lines:
                    lines.append("")
                if in_list:
                    indent = "    " * (current_list_nesting + 1)
                    lines.append(f"{indent}<!-- -->")
                else:
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
                    this_list_id = bullet.list_id
                    if not in_list or this_list_id != current_list_id:
                        list_counters = {}
                    nesting = _list_item_nesting_level(
                        para, list_defs.get(this_list_id or "")
                    )
                    # Drop counters at levels deeper than the current one so
                    # that re-entering a nested level restarts its numbering.
                    for lvl in list(list_counters.keys()):
                        if lvl > nesting:
                            del list_counters[lvl]
                    ordinal = list_counters.get(nesting, 0) + 1
                    list_counters[nesting] = ordinal
                    line = _serialize_list_item(
                        para, list_types, list_defs, ordinal=ordinal, heading_id_to_name=h_map, inline_objects=inline_objects
                    )
                    if line is not None:
                        if lines and (not in_list or this_list_id != current_list_id):
                            lines.append("")
                        lines.append(line)
                        in_list = True
                        current_list_id = this_list_id
                        current_list_nesting = nesting
                    continue
                else:
                    if in_list:
                        in_list = False
                        current_list_id = None
                    block = _serialize_paragraph(para, heading_id_to_name=h_map, inline_objects=inline_objects)
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


def _serialize_paragraph(
    para: Paragraph, *, heading_id_to_name: dict[str, str] | None = None, inline_objects: dict[str, Any] | None = None
) -> str | None:
    inline = _serialize_inlines(para.elements or [], heading_id_to_name=heading_id_to_name, inline_objects=inline_objects).rstrip()
    if not inline:
        return None

    ps = para.paragraph_style
    named_style = ps.named_style_type.value if ps and ps.named_style_type else None
    prefix = _STYLE_TO_HEADING.get(named_style or "")
    if prefix:
        return f"{prefix} {inline}"
    return inline


def _serialize_list_item(
    para: Paragraph,
    list_types: dict[str, str],
    list_defs: dict[str, Any],
    ordinal: int = 1,
    heading_id_to_name: dict[str, str] | None = None,
    inline_objects: dict[str, Any] | None = None,
) -> str | None:
    bullet = para.bullet
    if not bullet:
        return None

    inline = _serialize_inlines(para.elements or [], heading_id_to_name=heading_id_to_name, inline_objects=inline_objects).rstrip()
    list_id = bullet.list_id or ""
    nesting = _list_item_nesting_level(para, list_defs.get(list_id))
    list_type = list_types.get(list_id, "bullet")
    # 4 spaces per nesting level: CommonMark requires nested-list indentation
    # to reach the content column of the parent item's marker.  "1. " puts
    # content at column 3, "10. " at column 4, so 2-space indentation silently
    # flattens ordered sub-lists.  4 spaces is safe for both ordered and
    # unordered lists and for marker widths up to "99. ".
    indent = "    " * nesting

    if list_type == "decimal":
        return f"{indent}{ordinal}. {inline}"
    elif list_type == "checkbox":
        return f"{indent}- [ ] {inline}"
    else:
        return f"{indent}- {inline}"


def _list_item_nesting_level(para: Paragraph, list_def: Any) -> int:
    bullet = para.bullet
    if bullet and bullet.nesting_level is not None:
        return bullet.nesting_level
    ps = para.paragraph_style
    indent_start = ps.indent_start if ps else None
    if not indent_start or indent_start.magnitude is None:
        return 0
    target_magnitude = indent_start.magnitude
    target_unit = indent_start.unit or "PT"

    if isinstance(list_def, dict):
        nesting_levels = list_def.get("listProperties", {}).get("nestingLevels", [])
        for index, level in enumerate(nesting_levels):
            level_indent = level.get("indentStart", {})
            if (
                isinstance(level_indent, dict)
                and level_indent.get("magnitude") == target_magnitude
                and level_indent.get("unit", "PT") == target_unit
            ):
                return index
        return 0

    list_properties = getattr(list_def, "list_properties", None)
    nesting_levels = (list_properties.nesting_levels or []) if list_properties else []
    for index, level in enumerate(nesting_levels):
        level_indent = level.indent_start
        if not level_indent or level_indent.magnitude is None:
            continue
        if (
            level_indent.magnitude == target_magnitude
            and (level_indent.unit or "PT") == target_unit
        ):
            return index
    return 0


# ---------------------------------------------------------------------------
# Inline serialization
# ---------------------------------------------------------------------------


def _serialize_inlines(
    elements: list[ParagraphElement],
    *,
    heading_id_to_name: dict[str, str] | None = None,
    inline_objects: dict[str, Any] | None = None,
) -> str:
    return "".join(_serialize_inline_elem(pe, heading_id_to_name=heading_id_to_name, inline_objects=inline_objects) for pe in elements)


def _serialize_inline_elem(
    pe: ParagraphElement, *, heading_id_to_name: dict[str, str] | None = None, inline_objects: dict[str, Any] | None = None
) -> str:
    if pe.text_run is not None:
        return serialize_text_run(pe.text_run, heading_id_to_name=heading_id_to_name)

    if pe.inline_object_element is not None:
        obj_id = pe.inline_object_element.inline_object_id or ""
        io_dict = inline_objects or {}
        obj = io_dict.get(obj_id)
        uri = ""
        alt = ""
        if obj is not None:
            props = getattr(obj, "inline_object_properties", None)
            if props is None and isinstance(obj, dict):
                props_d = obj.get("inlineObjectProperties", {})
                eo_d = props_d.get("embeddedObject", {}) if props_d else {}
                uri = (eo_d.get("imageProperties", {}) or {}).get("contentUri", "") or ""
                alt = eo_d.get("description", "") or ""
            elif props is not None:
                eo = props.embedded_object
                if eo is not None:
                    uri = (eo.image_properties.content_uri or "") if eo.image_properties else ""
                    alt = eo.description or ""
        safe_alt = alt.replace("\\", "\\\\").replace("]", "\\]")
        safe_uri = uri.replace("\\", "\\\\").replace(")", "\\)")
        return f"![{safe_alt}]({safe_uri})"

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
        rich_props = pe.rich_link.rich_link_properties
        url = (rich_props.uri or "") if rich_props else ""
        title = (rich_props.title or "") if rich_props else ""
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


# ---------------------------------------------------------------------------
# Table serialization
# ---------------------------------------------------------------------------


def _serialize_table(table: Table, *, heading_id_to_name: dict[str, str] | None = None, inline_objects: dict[str, Any] | None = None) -> str:
    if _needs_html_table(table):
        return _serialize_html_table(table, heading_id_to_name=heading_id_to_name, inline_objects=inline_objects)
    return _serialize_gfm_table(table, heading_id_to_name=heading_id_to_name, inline_objects=inline_objects)


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


def _cell_text(cell: Any, *, heading_id_to_name: dict[str, str] | None = None, inline_objects: dict[str, Any] | None = None) -> str:
    parts: list[str] = []
    for se in cell.content or []:
        if se.paragraph:
            t = _serialize_inlines(se.paragraph.elements or [], heading_id_to_name=heading_id_to_name, inline_objects=inline_objects)
            if t:
                parts.append(t)
    return " ".join(parts).replace("|", "\\|")


def _serialize_gfm_table(table: Table, *, heading_id_to_name: dict[str, str] | None = None, inline_objects: dict[str, Any] | None = None) -> str:
    rows = table.table_rows or []
    if not rows:
        return ""

    cells = [[_cell_text(c, heading_id_to_name=heading_id_to_name, inline_objects=inline_objects) for c in row.table_cells or []] for row in rows]
    n_cols = max((len(r) for r in cells), default=0)
    for row in cells:
        while len(row) < n_cols:
            row.append("")

    header = "| " + " | ".join(cells[0]) + " |"
    sep = "| " + " | ".join("---" for _ in range(n_cols)) + " |"
    data = ["| " + " | ".join(row) + " |" for row in cells[1:]]
    return "\n".join([header, sep, *data])


def _serialize_html_table(table: Table, *, heading_id_to_name: dict[str, str] | None = None, inline_objects: dict[str, Any] | None = None) -> str:
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
            text = _cell_text(cell, heading_id_to_name=heading_id_to_name, inline_objects=inline_objects)
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
