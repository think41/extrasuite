"""Shared helpers for reconcile_v3 tests.

Provides lightweight factory functions to build synthetic Google Docs API
document structures using typed Pydantic models.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Body,
    Dimension,
    Document,
    DocumentTab,
    Footer,
    Footnote,
    Header,
    NamedStyle,
    NamedStyles,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableRow,
    TabProperties,
    TextRun,
    TextStyle,
)

# ---------------------------------------------------------------------------
# Paragraph helpers
# ---------------------------------------------------------------------------


def make_para_el(text: str, named_style: str = "NORMAL_TEXT") -> StructuralElement:
    """Return a content element containing a single paragraph."""
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        )
    )


def make_terminal_para() -> StructuralElement:
    """Return the terminal paragraph element (trailing newline)."""
    return make_para_el("\n")


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


def make_table_el(rows: list[list[str]]) -> StructuralElement:
    """Return a content element containing a table."""
    table_rows = []
    for row_texts in rows:
        cells = [
            TableCell(
                content=[make_para_el(t), make_terminal_para()],
            )
            for t in row_texts
        ]
        table_rows.append(TableRow(table_cells=cells))
    return StructuralElement(
        table=Table(
            table_rows=table_rows,
            columns=len(rows[0]) if rows else 0,
            rows=len(rows),
        )
    )


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------


def make_doc_tab(
    body_content: list[StructuralElement] | None = None,
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    lists: dict[str, object] | None = None,
    named_styles: list[NamedStyle] | None = None,
    document_style: dict[str, object] | None = None,
    inline_objects: dict[str, object] | None = None,
) -> DocumentTab:
    """Build a DocumentTab with sensible defaults."""
    if body_content is None:
        body_content = [make_terminal_para()]
    return DocumentTab(
        body=Body(content=body_content),
        headers=headers or {},
        footers=footers or {},
        footnotes=footnotes or {},
        lists=lists or {},
        named_styles=NamedStyles(styles=named_styles or []),
        document_style=document_style or {},
        inline_objects=inline_objects or {},
    )


def make_tab(
    tab_id: str,
    title: str = "Tab",
    index: int = 0,
    **kwargs: object,
) -> Tab:
    """Build a Tab with the given ID and DocumentTab content."""
    return Tab(
        tab_properties=TabProperties(tab_id=tab_id, title=title, index=index),
        document_tab=make_doc_tab(**kwargs),  # type: ignore[arg-type]
    )


def make_document(
    document_id: str = "doc1",
    tabs: list[Tab] | None = None,
) -> Document:
    """Build a minimal multi-tab Document."""
    if tabs is None:
        tabs = [make_tab("t1")]
    return Document(document_id=document_id, tabs=tabs)


def make_legacy_document(
    document_id: str = "doc1",
    body_content: list[StructuralElement] | None = None,
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    lists: dict[str, object] | None = None,
    named_styles: list[NamedStyle] | None = None,
    document_style: dict[str, object] | None = None,
) -> Document:
    """Build a legacy single-tab Document (body/headers at top level)."""
    if body_content is None:
        body_content = [make_terminal_para()]
    return Document(
        document_id=document_id,
        body=Body(content=body_content),
        headers=headers or {},
        footers=footers or {},
        footnotes=footnotes or {},
        lists=lists or {},
        named_styles=NamedStyles(styles=named_styles or []),
        document_style=document_style or {},
    )


# ---------------------------------------------------------------------------
# Named style helpers
# ---------------------------------------------------------------------------


def make_named_style(
    style_type: str,
    bold: bool = False,
    font_size: int | None = None,
) -> NamedStyle:
    """Build a NamedStyle with minimal properties."""
    text_style_kwargs: dict[str, object] = {}
    if bold:
        text_style_kwargs["bold"] = True
    if font_size is not None:
        text_style_kwargs["font_size"] = Dimension(magnitude=font_size, unit="PT")
    return NamedStyle(
        named_style_type=style_type,
        text_style=TextStyle(**text_style_kwargs),
        paragraph_style=ParagraphStyle(named_style_type=style_type),
    )


# ---------------------------------------------------------------------------
# Header / footer helpers
# ---------------------------------------------------------------------------


def make_header(header_id: str, text: str = "Header text") -> Header:
    """Build a Header."""
    return Header(
        header_id=header_id,
        content=[make_para_el(text), make_terminal_para()],
    )


def make_footer(footer_id: str, text: str = "Footer text") -> Footer:
    """Build a Footer."""
    return Footer(
        footer_id=footer_id,
        content=[make_para_el(text), make_terminal_para()],
    )


def make_footnote(footnote_id: str, text: str = "Footnote text") -> Footnote:
    """Build a Footnote."""
    return Footnote(
        footnote_id=footnote_id,
        content=[make_para_el(text), make_terminal_para()],
    )


# ---------------------------------------------------------------------------
# Indexed helpers (for lowering tests with start/end indices)
# ---------------------------------------------------------------------------


def make_indexed_para(
    text: str,
    start: int,
    named_style: str = "NORMAL_TEXT",
) -> StructuralElement:
    """Return a paragraph content element with Google Docs API index fields."""
    from extradoc.indexer import utf16_len

    end = start + utf16_len(text)
    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        ),
    )


def make_indexed_terminal(start: int) -> StructuralElement:
    """Return a terminal paragraph element (bare '\\n') with index fields."""
    return make_indexed_para("\n", start)


def make_indexed_doc(
    tab_id: str = "t1",
    body_content: list[StructuralElement] | None = None,
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    document_style: dict[str, object] | None = None,
    named_styles: list[NamedStyle] | None = None,
) -> Document:
    """Build a minimal indexed Document for lowering tests."""
    if body_content is None:
        body_content = [make_indexed_terminal(1)]
    return make_document(
        tabs=[
            make_tab(
                tab_id,
                body_content=body_content,
                headers=headers,
                footers=footers,
                footnotes=footnotes,
                document_style=document_style,
                named_styles=named_styles,
            )
        ]
    )
