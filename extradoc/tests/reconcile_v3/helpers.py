"""Shared helpers for reconcile_v3 tests.

Provides lightweight factory functions to build synthetic Google Docs API
document dicts without needing to touch any live APIs.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Paragraph helpers
# ---------------------------------------------------------------------------


def make_para_el(text: str, named_style: str = "NORMAL_TEXT") -> dict[str, Any]:
    """Return a content element dict containing a single paragraph."""
    return {
        "paragraph": {
            "elements": [{"textRun": {"content": text}}],
            "paragraphStyle": {"namedStyleType": named_style},
        }
    }


def make_terminal_para() -> dict[str, Any]:
    """Return the terminal paragraph element (trailing newline)."""
    return make_para_el("\n")


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


def make_table_el(rows: list[list[str]]) -> dict[str, Any]:
    """Return a content element dict containing a table."""
    table_rows = []
    for row_texts in rows:
        cells = [
            {
                "content": [make_para_el(t), make_terminal_para()],
                "tableCellStyle": {},
            }
            for t in row_texts
        ]
        table_rows.append({"tableCells": cells, "tableRowStyle": {}})
    return {
        "table": {
            "tableRows": table_rows,
            "columns": len(rows[0]) if rows else 0,
            "rows": len(rows),
        }
    }


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------


def make_doc_tab(
    body_content: list[dict[str, Any]] | None = None,
    headers: dict[str, Any] | None = None,
    footers: dict[str, Any] | None = None,
    footnotes: dict[str, Any] | None = None,
    lists: dict[str, Any] | None = None,
    named_styles: list[dict[str, Any]] | None = None,
    document_style: dict[str, Any] | None = None,
    inline_objects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a documentTab dict with sensible defaults."""
    if body_content is None:
        body_content = [make_terminal_para()]
    return {
        "body": {"content": body_content},
        "headers": headers or {},
        "footers": footers or {},
        "footnotes": footnotes or {},
        "lists": lists or {},
        "namedStyles": {"styles": named_styles or []},
        "documentStyle": document_style or {},
        "inlineObjects": inline_objects or {},
    }


def make_tab(
    tab_id: str,
    title: str = "Tab",
    index: int = 0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a tab dict with the given ID and documentTab content."""
    return {
        "tabProperties": {"tabId": tab_id, "title": title, "index": index},
        "documentTab": make_doc_tab(**kwargs),
    }


def make_document(
    document_id: str = "doc1",
    tabs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal multi-tab document dict."""
    if tabs is None:
        tabs = [make_tab("t1")]
    return {"documentId": document_id, "tabs": tabs}


def make_legacy_document(
    document_id: str = "doc1",
    body_content: list[dict[str, Any]] | None = None,
    headers: dict[str, Any] | None = None,
    footers: dict[str, Any] | None = None,
    footnotes: dict[str, Any] | None = None,
    lists: dict[str, Any] | None = None,
    named_styles: list[dict[str, Any]] | None = None,
    document_style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a legacy single-tab document dict (no 'tabs' field)."""
    if body_content is None:
        body_content = [make_terminal_para()]
    return {
        "documentId": document_id,
        "body": {"content": body_content},
        "headers": headers or {},
        "footers": footers or {},
        "footnotes": footnotes or {},
        "lists": lists or {},
        "namedStyles": {"styles": named_styles or []},
        "documentStyle": document_style or {},
    }


# ---------------------------------------------------------------------------
# Named style helpers
# ---------------------------------------------------------------------------


def make_named_style(
    style_type: str,
    bold: bool = False,
    font_size: int | None = None,
) -> dict[str, Any]:
    """Build a named style dict with minimal properties."""
    text_style: dict[str, Any] = {}
    if bold:
        text_style["bold"] = True
    if font_size is not None:
        text_style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
    return {
        "namedStyleType": style_type,
        "textStyle": text_style,
        "paragraphStyle": {"namedStyleType": style_type},
    }


# ---------------------------------------------------------------------------
# Header / footer helpers
# ---------------------------------------------------------------------------


def make_header(header_id: str, text: str = "Header text") -> dict[str, Any]:
    """Build a header dict."""
    return {
        "headerId": header_id,
        "content": [make_para_el(text), make_terminal_para()],
    }


def make_footer(footer_id: str, text: str = "Footer text") -> dict[str, Any]:
    """Build a footer dict."""
    return {
        "footerId": footer_id,
        "content": [make_para_el(text), make_terminal_para()],
    }


def make_footnote(footnote_id: str, text: str = "Footnote text") -> dict[str, Any]:
    """Build a footnote dict."""
    return {
        "footnoteId": footnote_id,
        "content": [make_para_el(text), make_terminal_para()],
    }
