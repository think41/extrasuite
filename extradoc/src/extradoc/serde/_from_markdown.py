"""Markdown → Document deserialization.

Parses a markdown file and converts it to a Google Docs Document API object.
The resulting Document has NO indices set — call reindex_document() if needed.

Handled:
  - Headings (# → HEADING_1, ## → HEADING_2, etc.)
  - Normal paragraphs with bold/italic/strikethrough/underline/<u>
  - Hyperlinks
  - Bullet (-), numbered (1.) lists with nesting
  - GFM pipe tables
  - HTML <table> blocks (passthrough — cell content is parsed)
  - Horizontal rules (---)
  - Page breaks (<x-pagebreak/>)
  - Passthrough tokens: <x-img>, <x-person>, <x-fn>, <x-chip>,
    <x-colbreak/>, <x-date/>, <x-auto/>, <x-eq/>
  - Footnote references [^id] and definitions [^id]: text
  - <!-- toc --> read-only marker
  - Fenced code blocks (```lang ... ```) → 1x1 table + named range
  - Callouts (> [!WARNING] ...) → 1x1 table + named range
  - Blockquotes (> text) → 1x1 table + named range
  - Inline code (`code`) → Courier New text run
"""

from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser
from typing import Any

from mistletoe.block_token import CodeFence, Heading, HTMLBlock, Quote, ThematicBreak
from mistletoe.block_token import Document as MdDocument
from mistletoe.block_token import List as MdList
from mistletoe.block_token import Paragraph as MdParagraph
from mistletoe.block_token import Table as MdTable
from mistletoe.html_renderer import HtmlRenderer
from mistletoe.span_token import (
    Emphasis,
    EscapeSequence,
    HTMLSpan,
    InlineCode,
    LineBreak,
    RawText,
    Strikethrough,
    Strong,
)
from mistletoe.span_token import Link as MdLink

from extradoc.api_types._generated import (
    AutoText,
    Bullet,
    ColumnBreak,
    DateElement,
    Document,
    DocumentTab,
    Equation,
    FootnoteReference,
    HorizontalRule,
    InlineObjectElement,
    PageBreak,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    Person,
    PersonProperties,
    RichLink,
    RichLinkProperties,
    SectionBreak,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableCellStyle,
    TableOfContents,
    TableRow,
    TabProperties,
    TextRun,
    TextStyle,
)
from extradoc.api_types._generated import (
    Link as DocLink,
)
from extradoc.mock.reindex import reindex_and_normalize_all_tabs
from extradoc.serde._special_elements import (
    Blockquote,
    Callout,
    CodeBlock,
    SpecialElement,
)
from extradoc.serde._utils import hex_to_optional_color

# Callout detection regex: matches [!WARNING], [!INFO], etc.
_CALLOUT_RE = re.compile(r"^\[!(WARNING|INFO|NOTE|DANGER|TIP)\]$", re.IGNORECASE)

# Heading level → named style type
_LEVEL_TO_NAMED_STYLE: dict[int, ParagraphStyleNamedStyleType] = {
    1: ParagraphStyleNamedStyleType.HEADING_1,
    2: ParagraphStyleNamedStyleType.HEADING_2,
    3: ParagraphStyleNamedStyleType.HEADING_3,
    4: ParagraphStyleNamedStyleType.HEADING_4,
    5: ParagraphStyleNamedStyleType.HEADING_5,
    6: ParagraphStyleNamedStyleType.HEADING_6,
}

# Synthetic list properties for markdown-derived lists
_SYNTH_LIST_PROPS: dict[str, dict[str, Any]] = {
    "bullet": {"listProperties": {"nestingLevels": [{"glyphSymbol": "●"}]}},
    "decimal": {"listProperties": {"nestingLevels": [{"glyphType": "DECIMAL"}]}},
    "checkbox": {"listProperties": {"nestingLevels": [{"glyphSymbol": "☐"}]}},
}

# Passthrough token regexes
_X_IMG_RE = re.compile(r'<x-img\s+id="([^"]+)"\s*/>', re.I)
_X_PERSON_RE = re.compile(
    r'<x-person\s+email="([^"]*)"(?:\s+name="([^"]*)")?\s*/>', re.I
)
_X_FN_RE = re.compile(r'<x-fn\s+id="([^"]+)"\s*/>', re.I)
_X_CHIP_RE = re.compile(r'<x-chip\s+url="([^"]*)"(?:\s+title="([^"]*)")?\s*/>', re.I)
_X_PAGEBREAK_RE = re.compile(r"<x-pagebreak\s*/>", re.I)
_X_COLBREAK_RE = re.compile(r"<x-colbreak\s*/>", re.I)
_X_DATE_RE = re.compile(r"<x-date\s*/>", re.I)
_X_AUTO_RE = re.compile(r"<x-auto\s*/>", re.I)
_X_EQ_RE = re.compile(r"<x-eq\s*/>", re.I)

# Footnote definition at start of line: [^id]: text
_FN_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)", re.MULTILINE)
_FN_REF_RE = re.compile(r"\[\^([^\]]+)\]")


# ---------------------------------------------------------------------------
# List ID synthesis
# ---------------------------------------------------------------------------


class _ListSynth:
    """Assigns stable synthetic list IDs during markdown parsing."""

    def __init__(self) -> None:
        self._counter = 0
        self._defs: dict[str, Any] = {}

    def new_list(self, list_type: str) -> str:
        self._counter += 1
        # Encode list_type in the ID so that changing list type (e.g. bullet →
        # decimal) produces a different ID.  The 3-way merge diff compares
        # ancestor vs mine list IDs: if they differ, a DeleteListOp + InsertListOp
        # is emitted, which correctly propagates the type change to the desired doc.
        list_id = f"kix.md_list_{list_type}_{self._counter}"
        self._defs[list_id] = _SYNTH_LIST_PROPS.get(
            list_type, _SYNTH_LIST_PROPS["bullet"]
        )
        return list_id

    @property
    def defs(self) -> dict[str, Any]:
        return dict(self._defs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def markdown_to_document(
    tab_content: dict[str, str],
    document_id: str = "",
    title: str = "",
    revision_id: str | None = None,
    tab_ids: dict[str, str] | None = None,
) -> Document:
    """Convert per-tab markdown content to a Document.

    Args:
        tab_content: dict[folder_name → markdown_source]
        document_id: Optional document ID
        title: Optional document title
        tab_ids: Optional dict[folder_name → tab_id] for using real API tab IDs

    Returns:
        Document without indices. Call reindex_document() if needed.
    """

    doc = Document.model_validate({"documentId": document_id, "title": title})
    if revision_id:
        doc.revision_id = revision_id
    doc.tabs = []

    for folder, source in tab_content.items():
        # Derive tab title from folder name
        tab_title = folder.replace("_", " ")
        tab_id = (tab_ids or {}).get(folder, f"t.{folder}")
        tab = _parse_tab(source, tab_title, folder, tab_id=tab_id)
        doc.tabs.append(tab)

    return doc


def _parse_tab(source: str, tab_title: str, folder: str, *, tab_id: str = "") -> Tab:
    """Parse a single tab's markdown source into a Tab.

    If the source contains special elements (code blocks, callouts, blockquotes),
    the returned Tab's DocumentTab will have named_ranges populated with correct
    indices (obtained by running reindex internally).
    """
    list_synth = _ListSynth()
    body_content, footnotes, special_positions = _parse_body(source, list_synth)

    # Build list definitions dict
    lists_d = list_synth.defs

    doc_tab_d: dict[str, Any] = {}
    if body_content:
        doc_tab_d["body"] = {
            "content": [
                se.model_dump(by_alias=True, exclude_none=True) for se in body_content
            ]
        }
    if lists_d:
        doc_tab_d["lists"] = lists_d
    if footnotes:
        doc_tab_d["footnotes"] = footnotes  # already plain dicts from _parse_body

    actual_tab_id = tab_id or f"t.{folder}"
    tab_props = TabProperties(tab_id=actual_tab_id, title=tab_title)
    doc_tab = DocumentTab.model_validate(doc_tab_d)
    tab = Tab(tab_properties=tab_props, document_tab=doc_tab)

    if not special_positions:
        return tab

    # Reindex the tab to assign real start/end indices, then embed named ranges.
    temp_doc_dict: dict[str, Any] = {
        "documentId": "",
        "tabs": [tab.model_dump(by_alias=True, exclude_none=True)],
    }
    reindex_and_normalize_all_tabs(temp_doc_dict)

    reindexed_tabs = temp_doc_dict.get("tabs") or []
    reindexed_body: list[Any] = []
    if reindexed_tabs:
        reindexed_body = (
            reindexed_tabs[0].get("documentTab", {}).get("body", {}).get("content", [])
        )

    # Build namedRanges dict from special positions + reindexed indices
    named_ranges_d: dict[str, Any] = {}
    for body_pos, nr_name in special_positions:
        if body_pos < len(reindexed_body):
            se_dict = reindexed_body[body_pos]
            si = se_dict.get("startIndex")
            ei = se_dict.get("endIndex")
            if si is not None and ei is not None:
                nr_entry = {
                    "namedRangeId": f"kix.md_nr_{body_pos}",
                    "name": nr_name,
                    "ranges": [{"startIndex": si, "endIndex": ei}],
                }
                group = named_ranges_d.setdefault(
                    nr_name, {"name": nr_name, "namedRanges": []}
                )
                group["namedRanges"].append(nr_entry)

    if not named_ranges_d:
        return tab

    # Rebuild DocumentTab from the reindexed version so that body elements carry
    # their startIndex — required by _build_named_range_index in _to_markdown.py.
    reindexed_dt_dict = (
        reindexed_tabs[0].get("documentTab", {}) if reindexed_tabs else {}
    )
    reindexed_dt_dict["namedRanges"] = named_ranges_d
    new_dt = DocumentTab.model_validate(reindexed_dt_dict)
    return Tab(tab_properties=tab_props, document_tab=new_dt)


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------


def _parse_body(
    source: str, list_synth: _ListSynth
) -> tuple[list[StructuralElement], dict[str, Any], list[tuple[int, str]]]:
    """Parse markdown source into body StructuralElements and footnotes.

    Returns:
        (body_content, footnote_dict, special_positions)
        body_content starts with a SectionBreak and ends with a trailing paragraph.
        special_positions: list of (body_index, named_range_name) for each special
        element (code block, callout, blockquote) inserted into the body.
    """
    # Extract footnote definitions before parsing (they live at the top level)
    fn_defs: dict[str, str] = {}
    for m in _FN_DEF_RE.finditer(source):
        fn_defs[m.group(1)] = m.group(2).strip()

    # Parse with mistletoe
    with HtmlRenderer():
        md_doc = MdDocument(source)

    body: list[StructuralElement] = []
    special_positions: list[tuple[int, str]] = []

    # Every body starts with a SectionBreak
    body.append(StructuralElement(section_break=SectionBreak()))

    for block in md_doc.children:
        if isinstance(block, Heading):
            body.append(_convert_heading(block))

        elif isinstance(block, CodeFence):
            body_pos = len(body)
            elem = _parse_code_fence(block)
            special_positions.append((body_pos, elem.named_range_name))
            prev_is_sb = body[-1].section_break is not None
            body.append(StructuralElement(table=elem.to_table()))
            # insertTable always displaces the preceding paragraph's trailing \n
            # to a post-table separator paragraph.  Model it explicitly so that
            # reindex_document assigns correct indices to subsequent elements and
            # verify() can compare them against the actual pushed document.
            # Only add when the table follows a real paragraph (not a SectionBreak)
            # — the SB case uses a different insertion path with no displacement.
            if not prev_is_sb:
                body.append(_make_trailing_para())

        elif isinstance(block, Quote):
            body_pos = len(body)
            elem = _parse_quote(block)
            special_positions.append((body_pos, elem.named_range_name))
            prev_is_sb = body[-1].section_break is not None
            body.append(StructuralElement(table=elem.to_table()))
            if not prev_is_sb:
                body.append(_make_trailing_para())

        elif isinstance(block, MdParagraph):
            # Check if this is a footnote definition line — skip it
            # (mistletoe may parse [^id]: text as a paragraph)
            text = _raw_text(block)
            if _FN_DEF_RE.match(text):
                continue
            ses = _convert_paragraph(block)
            body.extend(ses)

        elif isinstance(block, MdList):
            body.extend(_convert_list(block, list_synth, list_id=None, nesting=0))

        elif isinstance(block, MdTable):
            prev_is_sb = body[-1].section_break is not None
            body.append(_convert_gfm_table(block))
            if not prev_is_sb:
                body.append(_make_trailing_para())

        elif isinstance(block, ThematicBreak):
            body.append(_make_hr_para())

        elif isinstance(block, HTMLBlock):
            raw = block.content.strip()
            # page break
            if _X_PAGEBREAK_RE.match(raw):
                body.append(_make_pagebreak_para())
            elif raw == "<!-- -->":
                # Empty-paragraph placeholder emitted by _to_markdown for colored
                # empty paragraphs that cannot be represented in markdown.
                # Recreate as a plain empty paragraph to preserve structure.
                body.append(_make_trailing_para())
            elif raw == "<!-- toc -->":
                # Emit a synthetic tableOfContents element so the reconciler
                # sees a MATCHED TOC (not DELETED) and generates no requests.
                body.append(StructuralElement(table_of_contents=TableOfContents()))
            elif raw.lower().startswith("<table"):
                body.append(_convert_html_table(raw))
            else:
                # Try as a paragraph containing a single passthrough token
                pe = _parse_html_span(raw)
                if pe is not None:
                    body.append(
                        StructuralElement(
                            paragraph=Paragraph(
                                elements=[
                                    pe,
                                    ParagraphElement(text_run=TextRun(content="\n")),
                                ],
                                paragraph_style=ParagraphStyle(
                                    named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                                ),
                            )
                        )
                    )

    # Ensure trailing paragraph
    _ensure_trailing_paragraph(body)

    # Build footnote objects
    footnotes: dict[str, Any] = {}
    for fn_id, fn_text in fn_defs.items():
        fn_para = _make_text_para(fn_text)
        fn_obj = {
            "footnoteId": fn_id,
            "content": [fn_para.model_dump(by_alias=True, exclude_none=True)],
        }
        footnotes[fn_id] = fn_obj

    return body, footnotes, special_positions


# ---------------------------------------------------------------------------
# Special element converters (code fence, quote)
# ---------------------------------------------------------------------------


def _parse_code_fence(block: Any) -> CodeBlock:
    """Convert a mistletoe CodeFence token to a CodeBlock special element."""
    language = (getattr(block, "language", "") or "").strip()
    code_text = _raw_text(block)
    # Remove trailing newline that mistletoe typically adds
    if code_text.endswith("\n"):
        code_text = code_text[:-1]
    lines = code_text.split("\n")
    return CodeBlock(language=language, lines=lines)


def _block_to_para_groups(block: Any) -> list[list[Any]]:
    """Split a block's inline tokens at LineBreak boundaries.

    Each group (separated by LineBreak) will become a separate Paragraph in
    the callout or blockquote table cell, preserving the one-visual-line =
    one-paragraph mapping that the old _block_to_lines approach produced.
    """
    groups: list[list[Any]] = [[]]
    for token in getattr(block, "children", None) or []:
        if isinstance(token, LineBreak):
            groups.append([])
        else:
            groups[-1].append(token)
    return [g for g in groups if g]


def _tokens_to_para(tokens: list[Any]) -> Paragraph | None:
    """Convert a flat list of inline tokens to a Paragraph, or None if empty."""
    elements = _tokens_to_elements(tokens, TextStyle())
    if not elements:
        return None
    # Every paragraph in the Google Docs API must end with a "\n" text run.
    elements.append(ParagraphElement(text_run=TextRun(content="\n")))
    return Paragraph(
        elements=elements,
        paragraph_style=ParagraphStyle(
            named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
        ),
    )


def _parse_quote(block: Any) -> SpecialElement:
    """Convert a mistletoe Quote token to a Callout or Blockquote special element.

    Each visual line (separated by LineBreak within a paragraph, or by separate
    MdParagraph children) becomes one Paragraph in the table cell, preserving
    link styles, bold, italic, and other inline formatting.
    """
    children = list(block.children or [])
    if not children:
        return Blockquote(paragraphs=[])

    # Build a flat list of Paragraphs, splitting at LineBreak boundaries so
    # that each visual line maps to one table-cell paragraph.
    all_paras: list[Paragraph] = []
    for child in children:
        for group in _block_to_para_groups(child):
            para = _tokens_to_para(group)
            if para is not None:
                all_paras.append(para)

    if not all_paras:
        return Blockquote(paragraphs=[])

    # Check if the first paragraph is a callout type indicator: [!WARNING] etc.
    first_text = "".join(
        (pe.text_run.content or "")
        for pe in (all_paras[0].elements or [])
        if pe.text_run
    ).strip()
    m = _CALLOUT_RE.match(first_text)
    if m:
        variant_str = m.group(1).lower()
        variant = (
            variant_str
            if variant_str in ("warning", "info", "note", "danger", "tip")
            else "info"
        )  # type: ignore[assignment]
        # Keep only non-empty body paragraphs (mirrors old `if line` filter)
        body_paras = [
            p
            for p in all_paras[1:]
            if any((pe.text_run and pe.text_run.content) for pe in (p.elements or []))
        ]
        return Callout(variant=variant, paragraphs=body_paras)  # type: ignore[arg-type]

    # Plain blockquote — keep all non-empty paragraphs
    non_empty = [
        p
        for p in all_paras
        if any((pe.text_run and pe.text_run.content) for pe in (p.elements or []))
    ]
    return Blockquote(paragraphs=non_empty)


def _raw_text(block: Any) -> str:
    """Extract raw text from a block (best-effort)."""
    parts: list[str] = []
    for child in getattr(block, "children", None) or []:
        if hasattr(child, "content"):
            parts.append(str(child.content))
        parts.extend(_raw_text(child))
    return "".join(parts)


def _ensure_trailing_paragraph(body: list[StructuralElement]) -> None:
    """Ensure the body ends with a normal text paragraph (API requirement)."""
    if body and body[-1].paragraph is not None:
        last_p = body[-1].paragraph
        elems = last_p.elements or []
        if len(elems) == 1:
            tr = elems[0].text_run
            if tr and tr.content == "\n":
                return  # Already has trailing paragraph
    body.append(_make_trailing_para())


def _make_trailing_para() -> StructuralElement:
    return StructuralElement.model_validate(
        {
            "paragraph": {
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                },
                "elements": [{"textRun": {"content": "\n"}}],
            }
        }
    )


def _make_text_para(text: str) -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[
                ParagraphElement(text_run=TextRun(content=text + "\n")),
            ],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
            ),
        )
    )


def _make_hr_para() -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[
                ParagraphElement(horizontal_rule=HorizontalRule()),
                ParagraphElement(text_run=TextRun(content="\n")),
            ],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
            ),
        )
    )


def _make_pagebreak_para() -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[
                ParagraphElement(page_break=PageBreak()),
                ParagraphElement(text_run=TextRun(content="\n")),
            ],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Block converters
# ---------------------------------------------------------------------------


def _convert_heading(block: Any) -> StructuralElement:
    level = block.level
    named_style = _LEVEL_TO_NAMED_STYLE.get(
        level, ParagraphStyleNamedStyleType.HEADING_1
    )
    elements = _tokens_to_elements(block.children, TextStyle())
    elements.append(ParagraphElement(text_run=TextRun(content="\n")))
    return StructuralElement(
        paragraph=Paragraph(
            elements=elements,
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        )
    )


def _convert_paragraph(block: Any) -> list[StructuralElement]:
    """Convert a mistletoe Paragraph to one or more StructuralElements.

    A paragraph that contains only a <x-pagebreak/> becomes a pagebreak element.
    """
    # Check for a single page break token
    children = list(getattr(block, "children", []))
    if (
        len(children) == 1
        and isinstance(children[0], HTMLSpan)
        and _X_PAGEBREAK_RE.match(children[0].content)
    ):
        return [_make_pagebreak_para()]

    elements = _tokens_to_elements(children, TextStyle())
    if not elements:
        return []
    elements.append(ParagraphElement(text_run=TextRun(content="\n")))
    return [
        StructuralElement(
            paragraph=Paragraph(
                elements=elements,
                paragraph_style=ParagraphStyle(
                    named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                ),
            )
        )
    ]


def _convert_list(
    block: Any,
    list_synth: _ListSynth,
    list_id: str | None,
    nesting: int,
) -> list[StructuralElement]:
    """Convert a mistletoe List token to StructuralElements.

    Nested sub-lists reuse the same list_id at an increased nesting level.
    """
    list_type = "decimal" if block.start is not None else "bullet"
    if list_id is None:
        list_id = list_synth.new_list(list_type)

    result: list[StructuralElement] = []
    for item in block.children:
        item_children = list(item.children)

        # Separate inline content (first Paragraph) from nested Lists
        inline_tokens: list[Any] = []
        nested_lists: list[Any] = []

        for child in item_children:
            if isinstance(child, MdList):
                nested_lists.append(child)
            elif isinstance(child, MdParagraph):
                inline_tokens = list(child.children)
            # Other block types (quotes, etc.) are skipped for simplicity

        elements = _tokens_to_elements(inline_tokens, TextStyle())
        elements.append(ParagraphElement(text_run=TextRun(content="\n")))

        result.append(
            StructuralElement(
                paragraph=Paragraph(
                    elements=elements,
                    paragraph_style=ParagraphStyle(
                        named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                    ),
                    bullet=Bullet(list_id=list_id, nesting_level=nesting),
                )
            )
        )

        # Recurse into nested lists using same list_id
        for nested in nested_lists:
            result.extend(
                _convert_list(nested, list_synth, list_id=list_id, nesting=nesting + 1)
            )

    return result


def _convert_gfm_table(block: Any) -> StructuralElement:
    """Convert a mistletoe GFM Table to a Google Docs Table.

    The header row gets bold text to distinguish it from data rows.
    """
    all_rows: list[Any] = [block.header, *list(block.children)]
    n_cols = max((len(row.children) for row in all_rows), default=0)

    table_rows: list[TableRow] = []
    for row_idx, row in enumerate(all_rows):
        is_header = row_idx == 0
        cells: list[TableCell] = []
        for cell in row.children:
            base_style = TextStyle(bold=True) if is_header else TextStyle()
            inline_elements = _tokens_to_elements(list(cell.children), base_style)
            inline_elements.append(ParagraphElement(text_run=TextRun(content="\n")))
            cell_para = StructuralElement(
                paragraph=Paragraph(
                    elements=inline_elements,
                    paragraph_style=ParagraphStyle(
                        named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                    ),
                )
            )
            cells.append(
                TableCell(
                    content=[cell_para],
                    table_cell_style=TableCellStyle(),
                )
            )
        # Pad short rows
        while len(cells) < n_cols:
            pad_para = StructuralElement(
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content="\n"))],
                    paragraph_style=ParagraphStyle(
                        named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                    ),
                )
            )
            cells.append(
                TableCell(content=[pad_para], table_cell_style=TableCellStyle())
            )
        table_rows.append(TableRow(table_cells=cells))

    return StructuralElement(
        table=Table(
            rows=len(table_rows),
            columns=n_cols,
            table_rows=table_rows,
        )
    )


def _convert_html_table(raw_html: str) -> StructuralElement:
    """Convert an HTML <table> block to a Google Docs Table.

    Parses cell text content; ignores styling (handled by styles.xml separately).
    """

    class _TableParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.rows: list[list[dict[str, Any]]] = []
            self._in_cell = False
            self._colspan = 1
            self._rowspan = 1
            self._bg: str | None = None
            self._buf: list[str] = []

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if tag in ("tr",):
                self.rows.append([])
            elif tag in ("td", "th"):
                self._in_cell = True
                self._buf = []
                attr_d = dict(attrs)
                self._colspan = int(attr_d.get("colspan") or 1)
                self._rowspan = int(attr_d.get("rowspan") or 1)
                style = attr_d.get("style", "") or ""
                m = re.search(r"background-color:\s*(#[0-9a-fA-F]{6})", style)
                self._bg = m.group(1) if m else None

        def handle_endtag(self, tag: str) -> None:
            if tag in ("td", "th") and self._in_cell:
                self._in_cell = False
                if self.rows:
                    self.rows[-1].append(
                        {
                            "text": "".join(self._buf).strip(),
                            "colspan": self._colspan,
                            "rowspan": self._rowspan,
                            "bg": self._bg,
                        }
                    )

        def handle_data(self, data: str) -> None:
            if self._in_cell:
                self._buf.append(data)

    parser = _TableParser()
    parser.feed(raw_html)

    rows = [r for r in parser.rows if r]
    n_cols = max((sum(c["colspan"] for c in row) for row in rows), default=0)

    table_rows: list[TableRow] = []
    for row in rows:
        cells: list[TableCell] = []
        for cell_d in row:
            text = cell_d["text"]
            colspan = cell_d["colspan"]
            rowspan = cell_d["rowspan"]
            bg = cell_d["bg"]

            cell_para = StructuralElement(
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(text_run=TextRun(content=text + "\n")),
                    ],
                    paragraph_style=ParagraphStyle(
                        named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                    ),
                )
            )
            style_d: dict[str, Any] = {}
            if colspan > 1:
                style_d["columnSpan"] = colspan
            if rowspan > 1:
                style_d["rowSpan"] = rowspan
            if bg:
                style_d["backgroundColor"] = hex_to_optional_color(bg).model_dump(
                    by_alias=True, exclude_none=True
                )
            tcs = (
                TableCellStyle.model_validate(style_d) if style_d else TableCellStyle()
            )
            cells.append(TableCell(content=[cell_para], table_cell_style=tcs))
        table_rows.append(TableRow(table_cells=cells))

    return StructuralElement(
        table=Table(
            rows=len(table_rows),
            columns=n_cols,
            table_rows=table_rows,
        )
    )


# ---------------------------------------------------------------------------
# Inline token conversion
# ---------------------------------------------------------------------------


def _tokens_to_elements(tokens: list[Any], style: TextStyle) -> list[ParagraphElement]:
    """Recursively convert mistletoe inline tokens to ParagraphElements."""
    result: list[ParagraphElement] = []
    token_list = list(tokens)
    i = 0

    while i < len(token_list):
        token = token_list[i]

        if isinstance(token, RawText):
            # Strip U+000B (vertical tab / in-paragraph line break): mistletoe
            # also emits a LineBreak(soft=True) for the same position, which
            # will contribute a ' ' space run.  Keeping the vtab in the text
            # run content would cause a fingerprint mismatch against the base
            # (where vtabs are normalised to spaces in _normalize_paragraph).
            text = token.content.replace("\u000b", "")
            if text:
                result.extend(_raw_text_with_footnote_refs(text, style))

        elif isinstance(token, EscapeSequence):
            # Backslash-escaped character — treat as plain text
            text = "".join(
                c.content if isinstance(c, RawText) else ""
                for c in (token.children or [])
            )
            if text:
                result.append(_make_text_run(text, style))

        elif isinstance(token, Strong):
            new_style = style.model_copy(update={"bold": True})
            result.extend(_tokens_to_elements(token.children or [], new_style))

        elif isinstance(token, Emphasis):
            new_style = style.model_copy(update={"italic": True})
            result.extend(_tokens_to_elements(token.children or [], new_style))

        elif isinstance(token, Strikethrough):
            new_style = style.model_copy(update={"strikethrough": True})
            result.extend(_tokens_to_elements(token.children or [], new_style))

        elif isinstance(token, InlineCode):
            # Inline code → Courier New 10pt text run
            code_text = _raw_text(token)
            ts = TextStyle.model_validate(
                {
                    "weightedFontFamily": {"fontFamily": "Courier New"},
                    "fontSize": {"magnitude": 10, "unit": "PT"},
                }
            )
            if code_text:
                result.append(
                    ParagraphElement(text_run=TextRun(content=code_text, text_style=ts))
                )

        elif isinstance(token, MdLink):
            target = token.target
            if target.startswith("#heading:"):
                link_obj = DocLink(heading_id=target[len("#heading:") :])
            elif target.startswith("#bookmark:"):
                link_obj = DocLink(bookmark_id=target[len("#bookmark:") :])
            else:
                link_obj = DocLink(url=target)
            new_style = style.model_copy(update={"link": link_obj})
            result.extend(_tokens_to_elements(token.children or [], new_style))

        elif isinstance(token, HTMLSpan):
            content = token.content

            # Underline: <u>...</u> — stateful collection
            if content.lower() == "<u>":
                underline_tokens: list[Any] = []
                i += 1
                while i < len(token_list):
                    t = token_list[i]
                    if isinstance(t, HTMLSpan) and t.content.lower() == "</u>":
                        break
                    underline_tokens.append(t)
                    i += 1
                new_style = style.model_copy(update={"underline": True})
                result.extend(_tokens_to_elements(underline_tokens, new_style))

            elif content.lower() == "</u>":
                pass  # already consumed above

            else:
                # Try passthrough tokens
                pe = _parse_html_span(content)
                if pe is not None:
                    result.append(pe)

        elif isinstance(token, LineBreak):
            if token.soft:
                # Soft line break inside paragraph — represent as space
                result.append(_make_text_run(" ", style))

        i += 1

    return result


def _make_text_run(text: str, style: TextStyle) -> ParagraphElement:
    ts = style if _style_has_attrs(style) else None
    return ParagraphElement(text_run=TextRun(content=text, text_style=ts))


def _raw_text_with_footnote_refs(text: str, style: TextStyle) -> list[ParagraphElement]:
    elements: list[ParagraphElement] = []
    cursor = 0
    for match in _FN_REF_RE.finditer(text):
        if match.start() > cursor:
            elements.append(_make_text_run(text[cursor : match.start()], style))
        elements.append(
            ParagraphElement(
                footnote_reference=FootnoteReference(footnote_id=match.group(1))
            )
        )
        cursor = match.end()
    if cursor < len(text):
        elements.append(_make_text_run(text[cursor:], style))
    return elements


def _style_has_attrs(style: TextStyle) -> bool:
    return bool(
        style.bold
        or style.italic
        or style.strikethrough
        or style.underline
        or style.link
    )


def _parse_html_span(content: str) -> ParagraphElement | None:
    """Try to parse <x-*> passthrough tokens."""
    m = _X_IMG_RE.match(content)
    if m:
        return ParagraphElement(
            inline_object_element=InlineObjectElement(inline_object_id=m.group(1))
        )

    m = _X_PERSON_RE.match(content)
    if m:
        email = m.group(1)
        name = _html.unescape(m.group(2) or "") if m.group(2) else ""
        props = PersonProperties(email=email or None, name=name or None)
        return ParagraphElement(person=Person(person_properties=props))

    m = _X_FN_RE.match(content)
    if m:
        return ParagraphElement(
            footnote_reference=FootnoteReference(footnote_id=m.group(1))
        )

    m = _X_CHIP_RE.match(content)
    if m:
        url = m.group(1)
        title = _html.unescape(m.group(2) or "") if m.group(2) else ""
        props = RichLinkProperties(uri=url or None, title=title or None)
        return ParagraphElement(rich_link=RichLink(rich_link_properties=props))

    if _X_COLBREAK_RE.match(content):
        return ParagraphElement(column_break=ColumnBreak())

    if _X_DATE_RE.match(content):
        return ParagraphElement(date_element=DateElement())

    if _X_AUTO_RE.match(content):
        return ParagraphElement(auto_text=AutoText())

    if _X_EQ_RE.match(content):
        return ParagraphElement(equation=Equation())

    return None
