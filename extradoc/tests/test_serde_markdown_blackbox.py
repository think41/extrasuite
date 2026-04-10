"""Black-box tests for MarkdownSerde: serialize → edit → deserialize.

Every test follows the same pattern:
1. Load a real Google Docs API response (golden document.json)
2. Wrap it in a DocumentWithComments
3. Serialize it to a folder using MarkdownSerde
4. Make targeted edits to the markdown file(s)
5. Deserialize
6. Assert: (a) the edit is reflected in desired, (b) nothing else changed

The "nothing else changed" assertion is handled by `assert_preserved`, which
compares base vs desired for everything outside body content.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.serde.markdown import MarkdownSerde

GOLDEN_DIR = Path(__file__).parent / "golden"

# Our custom golden doc: headings, bold, italic, underline, strikethrough,
# bold+italic, external links, bullet list, numbered list, table.
MD_GOLDEN_ID = "1vL8dY0Ok__9VaUIqhBCMeElS5QdaKZfbgr_YCja5kx0"

# Existing golden: 3-tab doc with tables, HRs, headings, bold.
MULTITAB_GOLDEN_ID = "14nMj7vggV3XR3WQtYcgrABRABjKk-fqw0UQUCP25rhQ"

# Existing golden: 1-tab doc with lists, headings, bold.
LISTS_GOLDEN_ID = "1YicNYwId9u4okuK4uNfWdTEuKyS1QWb1RcnZl9eVyTc"

_serde = MarkdownSerde()


# ---------------------------------------------------------------------------
# Helpers: loading golden docs
# ---------------------------------------------------------------------------


def _load_golden(doc_id: str) -> Document:
    path = GOLDEN_DIR / f"{doc_id}.json"
    return Document.model_validate(json.loads(path.read_text()))


def _make_bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


# ---------------------------------------------------------------------------
# Helpers: RoundTrip harness
# ---------------------------------------------------------------------------


class RoundTrip:
    """Manage the serialize → edit → deserialize lifecycle."""

    def __init__(self, doc_id: str, folder: Path) -> None:
        self.doc = _load_golden(doc_id)
        self.bundle = _make_bundle(self.doc)
        self.folder = folder
        _serde.serialize(self.bundle, self.folder)

    def _tab_path(self, tab: str) -> Path:
        new = self.folder / "tabs" / f"{tab}.md"
        if new.exists():
            return new
        legacy = self.folder / f"{tab}.md"
        if legacy.exists():
            return legacy
        return new if (self.folder / "tabs").is_dir() else legacy

    def read_md(self, tab: str = "Tab_1") -> str:
        return self._tab_path(tab).read_text(encoding="utf-8")

    def write_md(self, content: str, tab: str = "Tab_1") -> None:
        self._tab_path(tab).write_text(content, encoding="utf-8")

    def edit_md(self, *, find: str, replace: str, tab: str = "Tab_1") -> None:
        md = self.read_md(tab)
        assert find in md, f"'{find}' not found in {tab}.md"
        self.write_md(md.replace(find, replace), tab)

    def deserialize(self):
        return _serde.deserialize(self.folder)


# ---------------------------------------------------------------------------
# Helpers: extraction from Document
# ---------------------------------------------------------------------------


def _tab_dt(doc: Document, tab_idx: int = 0):
    """Get documentTab for a tab index."""
    return doc.tabs[tab_idx].document_tab  # type: ignore[index]


def _body_content(doc: Document, tab_idx: int = 0):
    """Get body.content list for a tab."""
    dt = _tab_dt(doc, tab_idx)
    return dt.body.content or []  # type: ignore[union-attr]


def body_texts(doc: Document, tab_idx: int = 0) -> list[str]:
    """Extract non-empty paragraph texts (trailing \\n stripped)."""
    texts: list[str] = []
    for se in _body_content(doc, tab_idx):
        if se.paragraph:
            text = "".join(
                (pe.text_run.content or "").rstrip("\n")
                for pe in (se.paragraph.elements or [])
                if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
            )
            if text:
                texts.append(text)
    return texts


def body_para_styles(doc: Document, tab_idx: int = 0) -> list[str]:
    """Extract namedStyleType for each paragraph with text content."""
    styles: list[str] = []
    for se in _body_content(doc, tab_idx):
        if se.paragraph:
            text = "".join(
                (pe.text_run.content or "").rstrip("\n")
                for pe in (se.paragraph.elements or [])
                if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
            )
            if text:
                ps = se.paragraph.paragraph_style
                nst = ps.named_style_type if ps else "NORMAL_TEXT"
                styles.append(str(nst))
    return styles


def body_runs(doc: Document, tab_idx: int = 0, para_text: str = "") -> list[dict]:
    """Extract text runs from the first paragraph matching para_text.

    Returns list of dicts with keys: text, bold, italic, underline,
    strikethrough, link.
    """
    for se in _body_content(doc, tab_idx):
        if not se.paragraph:
            continue
        full_text = "".join(
            (pe.text_run.content or "").rstrip("\n")
            for pe in (se.paragraph.elements or [])
            if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
        )
        if para_text not in full_text:
            continue
        runs: list[dict] = []
        for pe in se.paragraph.elements or []:
            if not pe.text_run:
                continue
            content = pe.text_run.content or ""
            if content == "\n":
                continue
            ts = pe.text_run.text_style
            runs.append(
                {
                    "text": content,
                    "bold": bool(ts and ts.bold),
                    "italic": bool(ts and ts.italic),
                    "underline": bool(ts and ts.underline),
                    "strikethrough": bool(ts and ts.strikethrough),
                    "link": (ts.link.url or "") if ts and ts.link else "",
                }
            )
        return runs
    pytest.fail(f"No paragraph containing '{para_text}' found")


def table_cell_texts(doc: Document, tab_idx: int = 0) -> list[list[list[str]]]:
    """Extract cell texts from all tables.

    Returns list of tables, each table is list of rows, each row is list of
    cell texts.
    """
    tables: list[list[list[str]]] = []
    for se in _body_content(doc, tab_idx):
        if not se.table:
            continue
        rows: list[list[str]] = []
        for row in se.table.table_rows or []:
            row_texts: list[str] = []
            for cell in row.table_cells or []:
                cell_text = ""
                for cell_se in cell.content or []:
                    if cell_se.paragraph:
                        cell_text += "".join(
                            (pe.text_run.content or "").rstrip("\n")
                            for pe in (cell_se.paragraph.elements or [])
                            if pe.text_run
                        )
                row_texts.append(cell_text)
            rows.append(row_texts)
        tables.append(rows)
    return tables


def table_dimensions(doc: Document, tab_idx: int = 0) -> list[tuple[int, int]]:
    """Return (rows, cols) for each table in the document."""
    dims: list[tuple[int, int]] = []
    for se in _body_content(doc, tab_idx):
        if se.table:
            rows = len(se.table.table_rows or [])
            cols = se.table.columns or 0
            dims.append((rows, cols))
    return dims


def table_cell_runs(
    doc: Document, tab_idx: int = 0, table_idx: int = 0, row: int = 0, col: int = 0
) -> list[dict]:
    """Extract text runs from a specific table cell.

    Returns list of dicts with keys: text, bold, italic, underline, link.
    """
    table_count = 0
    for se in _body_content(doc, tab_idx):
        if not se.table:
            continue
        if table_count != table_idx:
            table_count += 1
            continue
        rows = se.table.table_rows or []
        assert row < len(rows), f"Row {row} out of range (table has {len(rows)} rows)"
        cells = rows[row].table_cells or []
        assert col < len(cells), f"Col {col} out of range (row has {len(cells)} cells)"
        runs: list[dict] = []
        for cell_se in cells[col].content or []:
            if not cell_se.paragraph:
                continue
            for pe in cell_se.paragraph.elements or []:
                if not pe.text_run:
                    continue
                content = pe.text_run.content or ""
                if content == "\n":
                    continue
                ts = pe.text_run.text_style
                runs.append(
                    {
                        "text": content,
                        "bold": bool(ts and ts.bold),
                        "italic": bool(ts and ts.italic),
                        "underline": bool(ts and ts.underline),
                        "link": (ts.link.url or "") if ts and ts.link else "",
                    }
                )
        return runs
    pytest.fail(f"Table index {table_idx} not found")


def body_list_items(doc: Document, tab_idx: int = 0) -> list[dict]:
    """Extract list items with their text and list ID.

    Returns list of dicts with keys: text, list_id, nesting_level.
    """
    items: list[dict] = []
    for se in _body_content(doc, tab_idx):
        if not se.paragraph or not se.paragraph.bullet:
            continue
        text = "".join(
            (pe.text_run.content or "").rstrip("\n")
            for pe in (se.paragraph.elements or [])
            if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
        )
        if text:
            items.append(
                {
                    "text": text,
                    "list_id": se.paragraph.bullet.list_id or "",
                    "nesting_level": se.paragraph.bullet.nesting_level or 0,
                }
            )
    return items


# ---------------------------------------------------------------------------
# Helpers: assert_preserved
# ---------------------------------------------------------------------------

_SYNTH_LIST_RE = re.compile(r"^kix\.md_list_")


def _strip_indices(obj: Any) -> Any:
    """Recursively strip startIndex/endIndex from a dict tree."""
    if isinstance(obj, dict):
        return {
            k: _strip_indices(v)
            for k, v in obj.items()
            if k not in ("startIndex", "endIndex")
        }
    if isinstance(obj, list):
        return [_strip_indices(item) for item in obj]
    return obj


def _strip_synthetic_lists(lists_dict: dict) -> dict:
    """Remove synthetic list definitions (kix.md_list_*) from a lists dict."""
    return {k: v for k, v in lists_dict.items() if not _SYNTH_LIST_RE.match(k)}


def assert_preserved(
    base_doc: Document,
    desired_doc: Document,
    *,
    edited_tabs: set[int] | None = None,
    skip_fields: set[str] | None = None,
) -> None:
    """Assert that non-body fields are identical between base and desired.

    For tabs NOT in edited_tabs: asserts the full documentTab (except body)
    is identical after stripping indices.

    For edited tabs: asserts all documentTab fields except 'body' and
    skip_fields are identical. The 'lists' field automatically filters out
    synthetic markdown list definitions (kix.md_list_*).

    Args:
        base_doc: The base document (from DeserializeResult.base)
        desired_doc: The desired document (from DeserializeResult.desired)
        edited_tabs: Tab indices where body edits were made (default: {0})
        skip_fields: documentTab field names to skip for edited tabs
    """
    if edited_tabs is None:
        edited_tabs = {0}
    if skip_fields is None:
        skip_fields = set()

    base_dict = _strip_indices(base_doc.model_dump(by_alias=True, exclude_none=True))
    desired_dict = _strip_indices(
        desired_doc.model_dump(by_alias=True, exclude_none=True)
    )

    # Top-level fields (title, documentId)
    for key in ("title", "documentId"):
        assert base_dict.get(key) == desired_dict.get(key), f"Top-level '{key}' changed"

    base_tabs = base_dict.get("tabs", [])
    desired_tabs = desired_dict.get("tabs", [])
    assert len(base_tabs) == len(desired_tabs), (
        f"Tab count changed: {len(base_tabs)} → {len(desired_tabs)}"
    )

    for i, (bt, dt) in enumerate(zip(base_tabs, desired_tabs, strict=True)):
        # Tab properties always preserved
        assert bt.get("tabProperties") == dt.get("tabProperties"), (
            f"Tab {i} tabProperties changed"
        )

        b_dt = bt.get("documentTab", {})
        d_dt = dt.get("documentTab", {})

        if i not in edited_tabs:
            # Non-edited tab: everything except body should match
            b_no_body = {k: v for k, v in b_dt.items() if k != "body"}
            d_no_body = {k: v for k, v in d_dt.items() if k != "body"}
            assert b_no_body == d_no_body, f"Non-edited tab {i} changed"
            # Body content count should also match for non-edited tabs
            b_body = b_dt.get("body", {}).get("content", [])
            d_body = d_dt.get("body", {}).get("content", [])
            assert len(b_body) == len(d_body), (
                f"Non-edited tab {i} body content count changed: "
                f"{len(b_body)} → {len(d_body)}"
            )
            continue

        # Edited tab: compare all documentTab fields except body + skip_fields
        all_keys = set(b_dt.keys()) | set(d_dt.keys())
        for key in sorted(all_keys):
            if key == "body" or key in skip_fields:
                continue

            b_val = b_dt.get(key)
            d_val = d_dt.get(key)

            # Special handling: strip synthetic list defs before comparison
            if key == "lists" and isinstance(b_val, dict) and isinstance(d_val, dict):
                b_val = _strip_synthetic_lists(b_val)
                d_val = _strip_synthetic_lists(d_val)

            assert b_val == d_val, f"Tab {i} documentTab.{key} changed unexpectedly"


# ===========================================================================
# Tests: No-op round-trip (serialize → deserialize, no edits)
# ===========================================================================


class TestNoOpRoundTrip:
    """Serialize then immediately deserialize with no edits.

    Desired must equal base for all non-body fields. Body content text
    must be identical.
    """

    def test_noop_md_golden(self, tmp_path: Path) -> None:
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        assert body_texts(result.base.document) == body_texts(result.desired.document)

    def test_noop_multitab_golden(self, tmp_path: Path) -> None:
        rt = RoundTrip(MULTITAB_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        assert_preserved(
            result.base.document,
            result.desired.document,
            edited_tabs={0, 1, 2},
        )
        for i in range(3):
            assert body_texts(result.base.document, i) == body_texts(
                result.desired.document, i
            )

    def test_noop_lists_golden(self, tmp_path: Path) -> None:
        rt = RoundTrip(LISTS_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        assert body_texts(result.base.document) == body_texts(result.desired.document)


# ===========================================================================
# Tests: Paragraph text edits
# ===========================================================================


class TestParagraphEdits:
    def test_edit_plain_paragraph(self, tmp_path: Path) -> None:
        """Edit text of a normal paragraph."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="This is a plain paragraph with no formatting.",
            replace="This is an edited paragraph.",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        texts = body_texts(result.desired.document)
        assert "This is an edited paragraph." in texts
        assert "This is a plain paragraph with no formatting." not in texts

    def test_add_paragraph(self, tmp_path: Path) -> None:
        """Add a new paragraph."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.\n",
            replace="Second plain paragraph.\n\nA brand new paragraph.\n",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        texts = body_texts(result.desired.document)
        assert "A brand new paragraph." in texts
        assert "Second plain paragraph." in texts

    def test_delete_paragraph(self, tmp_path: Path) -> None:
        """Delete a paragraph."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        lines = md.splitlines(keepends=True)
        lines = [line for line in lines if "Second plain paragraph." not in line]
        rt.write_md("".join(lines))
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        texts = body_texts(result.desired.document)
        assert "Second plain paragraph." not in texts
        assert "This is a plain paragraph with no formatting." in texts


# ===========================================================================
# Tests: Heading edits
# ===========================================================================


class TestHeadingEdits:
    def test_edit_heading_text(self, tmp_path: Path) -> None:
        """Edit the text of a heading."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="# Introduction\n", replace="# Overview\n")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        texts = body_texts(result.desired.document)
        assert "Overview" in texts
        assert "Introduction" not in texts

    def test_change_heading_level(self, tmp_path: Path) -> None:
        """Change heading from h2 to h3."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="## Formatting Section\n", replace="### Formatting Section\n")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        styles = body_para_styles(result.desired.document)
        texts = body_texts(result.desired.document)
        idx = texts.index("Formatting Section")
        assert styles[idx] == "HEADING_3"

    def test_add_heading(self, tmp_path: Path) -> None:
        """Add a new heading."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Final paragraph of the document.",
            replace="## New Section\n\nFinal paragraph of the document.",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        texts = body_texts(result.desired.document)
        styles = body_para_styles(result.desired.document)
        idx = texts.index("New Section")
        assert styles[idx] == "HEADING_2"


# ===========================================================================
# Tests: Formatting edits
# ===========================================================================


class TestFormattingEdits:
    def test_add_bold_to_existing_text(self, tmp_path: Path) -> None:
        """Make text bold in markdown."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.",
            replace="Second **plain** paragraph.",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="Second")
        bold_runs = [r for r in runs if r["bold"]]
        assert any("plain" in r["text"] for r in bold_runs)

    def test_add_italic_to_existing_text(self, tmp_path: Path) -> None:
        """Make text italic in markdown."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.",
            replace="Second *plain* paragraph.",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="Second")
        italic_runs = [r for r in runs if r["italic"]]
        assert any("plain" in r["text"] for r in italic_runs)

    def test_remove_bold(self, tmp_path: Path) -> None:
        """Remove bold formatting by removing ** markers."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="**bold text**", replace="bold text")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="bold text")
        bold_runs = [r for r in runs if r["bold"]]
        assert not any("bold text" in r["text"] for r in bold_runs)

    def test_underline_preserved_after_nearby_edit(self, tmp_path: Path) -> None:
        """Underline survives when a different paragraph is edited."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="underlined text")
        underline_runs = [r for r in runs if r["underline"]]
        assert any("underlined" in r["text"] for r in underline_runs)

    def test_strikethrough_preserved_after_nearby_edit(self, tmp_path: Path) -> None:
        """Strikethrough survives when a different paragraph is edited."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="strikethrough text")
        strike_runs = [r for r in runs if r["strikethrough"]]
        assert any("strikethrough" in r["text"] for r in strike_runs)

    def test_bold_italic_preserved_after_nearby_edit(self, tmp_path: Path) -> None:
        """Bold+italic survives when a different paragraph is edited."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="bold italic text")
        bi_runs = [r for r in runs if r["bold"] and r["italic"]]
        assert any("bold italic" in r["text"] for r in bi_runs)


# ===========================================================================
# Tests: Link edits
# ===========================================================================


class TestLinkEdits:
    def test_existing_links_preserved(self, tmp_path: Path) -> None:
        """Links survive no-op round-trip."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        runs = body_runs(result.desired.document, para_text="Example Website")
        link_runs = [r for r in runs if r["link"]]
        assert any("example.com" in r["link"] for r in link_runs)

    def test_edit_link_url(self, tmp_path: Path) -> None:
        """Change a link URL."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="[Example Website](https://example.com)",
            replace="[Example Website](https://example.org)",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="Example Website")
        link_runs = [r for r in runs if r["link"]]
        assert any("example.org" in r["link"] for r in link_runs)

    def test_edit_link_text(self, tmp_path: Path) -> None:
        """Change link display text."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="[Example Website](https://example.com)",
            replace="[Example Site](https://example.com)",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="Example Site")
        assert any(
            r["text"] == "Example Site" and "example.com" in r["link"] for r in runs
        )

    def test_add_new_link(self, tmp_path: Path) -> None:
        """Add a link to plain text."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.",
            replace="Second [plain](https://plain.com) paragraph.",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="Second plain paragraph")
        link_runs = [r for r in runs if r["link"]]
        assert any("plain.com" in r["link"] for r in link_runs)

    def test_remove_link(self, tmp_path: Path) -> None:
        """Remove a link (keep text, remove URL)."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="[Google](https://google.com)",
            replace="Google",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = body_runs(result.desired.document, para_text="Google")
        # "Google" text should exist but without a link
        google_runs = [r for r in runs if "Google" in r["text"]]
        assert google_runs  # text preserved
        assert not any("google.com" in r["link"] for r in google_runs)


# ===========================================================================
# Tests: List edits
# ===========================================================================


class TestListEdits:
    def test_edit_bullet_item_text(self, tmp_path: Path) -> None:
        """Edit text of a bullet list item."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="- First bullet item\n", replace="- First edited bullet\n")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        items = body_list_items(result.desired.document)
        assert any("First edited bullet" in i["text"] for i in items)

    def test_add_bullet_item(self, tmp_path: Path) -> None:
        """Add a new bullet list item."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="- Third bullet item\n",
            replace="- Third bullet item\n- Fourth bullet item\n",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        items = body_list_items(result.desired.document)
        assert any("Fourth bullet item" in i["text"] for i in items)

    def test_delete_bullet_item(self, tmp_path: Path) -> None:
        """Delete a bullet list item."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        lines = md.splitlines(keepends=True)
        lines = [line for line in lines if "Second bullet item" not in line]
        rt.write_md("".join(lines))
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        items = body_list_items(result.desired.document)
        assert not any("Second bullet item" in i["text"] for i in items)
        assert any("First bullet item" in i["text"] for i in items)
        assert any("Third bullet item" in i["text"] for i in items)

    def test_edit_numbered_item_text(self, tmp_path: Path) -> None:
        """Edit text of a numbered list item."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="1. First numbered item\n",
            replace="1. First edited number\n",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        items = body_list_items(result.desired.document)
        assert any("First edited number" in i["text"] for i in items)


# ===========================================================================
# Tests: Table edits (existing table in golden doc)
# ===========================================================================


class TestTableEdits:
    def test_edit_table_cell(self, tmp_path: Path) -> None:
        """Edit a table cell's text."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="| Alpha |", replace="| Omega |")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        assert len(tables) == 1
        assert tables[0][1][0] == "Omega"  # row 1, col 0

    def test_table_preserved_on_noop(self, tmp_path: Path) -> None:
        """Table structure is preserved when not edited."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        # Exact structure check
        tables = table_cell_texts(result.desired.document)
        assert len(tables) == 1
        assert tables[0] == [
            ["Name", "Value", "Description"],
            ["Alpha", "100", "The first item"],
            ["Beta", "200", "The second item"],
        ]

    def test_edit_header_row_cell(self, tmp_path: Path) -> None:
        """Edit a cell in the header row of an existing table."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="| Name |", replace="| Label |")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        assert tables[0][0][0] == "Label"
        # Other header cells unchanged
        assert tables[0][0][1] == "Value"
        assert tables[0][0][2] == "Description"

    def test_edit_multiple_cells(self, tmp_path: Path) -> None:
        """Edit multiple cells in the same table."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        md = md.replace("| Alpha |", "| Omega |")
        md = md.replace("| 200 |", "| 999 |")
        rt.write_md(md)
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        assert tables[0][1][0] == "Omega"
        assert tables[0][2][1] == "999"
        # Dimensions unchanged
        assert table_dimensions(result.desired.document) == [(3, 3)]

    def test_header_row_not_bolded_after_cell_edit(self, tmp_path: Path) -> None:
        """Editing a data cell must not introduce bold to the header row.

        The GFM spec renders header cells in bold, and the markdown parser
        models them as bold=True. But the 3-way merge should detect that the
        header didn't change and preserve it from base (which has no bold).
        """
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="| Alpha |", replace="| Omega |")
        result = rt.deserialize()
        # Header cells should have the same bold as base (None/False)
        runs = table_cell_runs(result.desired.document, row=0, col=0)
        assert runs, "Expected runs in header cell"
        assert not runs[0]["bold"], (
            "Header cell 'Name' gained bold=True after editing a data cell"
        )

    def test_header_row_not_bolded_after_non_table_edit(self, tmp_path: Path) -> None:
        """Editing a paragraph outside the table must not bold the header row."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()
        for ci in range(3):
            runs = table_cell_runs(result.desired.document, row=0, col=ci)
            assert runs
            assert not runs[0]["bold"], (
                f"Header cell [{ci}] gained bold after editing a non-table paragraph"
            )

    def test_table_structure_preserved_after_non_table_edit(
        self, tmp_path: Path
    ) -> None:
        """Editing a paragraph must not alter the table's internal structure.

        The table's tableStyle, tableCellStyle, and paragraphStyle should be
        preserved from base when the table content is not edited.
        """
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()

        def _strip_indices(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {
                    k: _strip_indices(v)
                    for k, v in obj.items()
                    if k not in ("startIndex", "endIndex")
                }
            if isinstance(obj, list):
                return [_strip_indices(item) for item in obj]
            return obj

        base_table = desired_table = None
        for se in _body_content(result.base.document):
            if se.table:
                base_table = _strip_indices(
                    se.model_dump(by_alias=True, exclude_none=True)
                )
        for se in _body_content(result.desired.document):
            if se.table:
                desired_table = _strip_indices(
                    se.model_dump(by_alias=True, exclude_none=True)
                )
        assert base_table is not None
        assert desired_table is not None
        assert base_table == desired_table, (
            "Table structure changed after editing a non-table paragraph"
        )


# ===========================================================================
# Tests: Multi-tab documents
# ===========================================================================


class TestMultiTab:
    def test_edit_one_tab_preserves_others(self, tmp_path: Path) -> None:
        """Edit tab 1 of a 3-tab doc, tabs 2 and 3 are unchanged."""
        rt = RoundTrip(MULTITAB_GOLDEN_ID, tmp_path / "doc")
        # Find the tab file names
        tabs_dir = rt.folder / "tabs" if (rt.folder / "tabs").is_dir() else rt.folder
        md_files = sorted(tabs_dir.glob("*.md"))
        tab_names = [f.stem for f in md_files if f.stem != "index"]
        assert len(tab_names) >= 2, f"Expected 2+ tabs, got {tab_names}"

        # Edit only the first tab
        first_tab = tab_names[0]
        md = rt.read_md(first_tab)
        # Just add a new paragraph at the end
        rt.write_md(md.rstrip() + "\n\nNew paragraph in tab one.\n", first_tab)

        result = rt.deserialize()
        # All tabs except the first should be fully preserved
        assert_preserved(
            result.base.document,
            result.desired.document,
            edited_tabs={0},
        )

    def test_noop_preserves_all_tabs(self, tmp_path: Path) -> None:
        """No edits on a multi-tab doc: all tabs preserved."""
        rt = RoundTrip(MULTITAB_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        for i in range(len(result.base.document.tabs or [])):
            base_texts = body_texts(result.base.document, i)
            desired_texts = body_texts(result.desired.document, i)
            assert base_texts == desired_texts, f"Tab {i} texts changed on no-op"


# ===========================================================================
# Tests: Preservation of things markdown doesn't model
# ===========================================================================


class TestPreservation:
    """Markdown doesn't model headers, footers, documentStyle, namedStyles,
    inlineObjects. These must survive the round-trip from base unchanged.
    """

    def test_document_style_preserved(self, tmp_path: Path) -> None:
        """documentStyle from base survives."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        base_ds = _tab_dt(result.base.document).document_style
        desired_ds = _tab_dt(result.desired.document).document_style
        assert base_ds is not None
        assert desired_ds is not None
        # Compare via dict to avoid object identity issues
        assert base_ds.model_dump(exclude_none=True) == desired_ds.model_dump(
            exclude_none=True
        )

    def test_named_styles_preserved(self, tmp_path: Path) -> None:
        """namedStyles from base survives."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        base_ns = _tab_dt(result.base.document).named_styles
        desired_ns = _tab_dt(result.desired.document).named_styles
        assert base_ns is not None
        assert desired_ns is not None
        assert base_ns.model_dump(exclude_none=True) == desired_ns.model_dump(
            exclude_none=True
        )

    def test_list_definitions_preserved(self, tmp_path: Path) -> None:
        """List definitions from base survive (synthetic ones excluded)."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        base_lists = _tab_dt(result.base.document).lists or {}
        desired_lists = _tab_dt(result.desired.document).lists or {}

        # Filter out synthetic markdown list defs
        base_ids = {k for k in base_lists if not _SYNTH_LIST_RE.match(k)}
        desired_ids = {k for k in desired_lists if not _SYNTH_LIST_RE.match(k)}
        assert base_ids == desired_ids

    def test_preservation_after_edit(self, tmp_path: Path) -> None:
        """Even after a body edit, non-body fields survive from base."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="Second plain paragraph.", replace="Edited paragraph.")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)


# ===========================================================================
# Tests: Using the lists-heavy golden doc
# ===========================================================================


class TestListsGolden:
    """Tests against the 1-tab golden doc with 53 bulleted items."""

    def test_edit_preserves_other_bullets(self, tmp_path: Path) -> None:
        """Editing one bullet item doesn't affect others."""
        rt = RoundTrip(LISTS_GOLDEN_ID, tmp_path / "doc")
        base_items = body_list_items(rt.bundle.document)
        # Find a bullet item to edit
        assert len(base_items) > 5
        target = base_items[2]["text"]

        rt.edit_md(find=target, replace="EDITED_ITEM")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)

        items = body_list_items(result.desired.document)
        assert any("EDITED_ITEM" in i["text"] for i in items)
        # Other items should still exist
        assert any(base_items[0]["text"] in i["text"] for i in items)
        assert any(base_items[4]["text"] in i["text"] for i in items)


# ===========================================================================
# Tests: HRs from the multi-tab golden doc
# ===========================================================================


class TestHorizontalRules:
    """The 3-tab golden doc has HRs. Markdown can't create or delete HRs,
    but they must survive the round-trip untouched.
    """

    def test_hr_count_preserved_on_noop(self, tmp_path: Path) -> None:
        """HR elements survive no-op round-trip."""
        rt = RoundTrip(MULTITAB_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()

        def _count_hrs(doc: Document, tab_idx: int) -> int:
            count = 0
            for se in _body_content(doc, tab_idx):
                if se.paragraph:
                    for pe in se.paragraph.elements or []:
                        if pe.horizontal_rule is not None:
                            count += 1
            return count

        for i in range(len(result.base.document.tabs or [])):
            base_hrs = _count_hrs(result.base.document, i)
            desired_hrs = _count_hrs(result.desired.document, i)
            assert base_hrs == desired_hrs, (
                f"Tab {i}: HR count changed {base_hrs} → {desired_hrs}"
            )

    def test_hr_preserved_after_edit(self, tmp_path: Path) -> None:
        """HRs survive even when body text is edited."""
        rt = RoundTrip(MULTITAB_GOLDEN_ID, tmp_path / "doc")
        # Find a text to edit in tab 0
        texts = body_texts(rt.bundle.document, 0)
        # Pick a non-heading text
        target = next(t for t in texts if len(t) > 10)
        tabs_dir = rt.folder / "tabs" if (rt.folder / "tabs").is_dir() else rt.folder
        first_tab = sorted(f.stem for f in tabs_dir.glob("*.md") if f.stem != "index")[
            0
        ]

        rt.edit_md(find=target, replace="Edited text here", tab=first_tab)
        result = rt.deserialize()

        def _count_hrs(doc: Document, tab_idx: int) -> int:
            count = 0
            for se in _body_content(doc, tab_idx):
                if se.paragraph:
                    for pe in se.paragraph.elements or []:
                        if pe.horizontal_rule is not None:
                            count += 1
            return count

        base_hrs = _count_hrs(result.base.document, 0)
        desired_hrs = _count_hrs(result.desired.document, 0)
        assert base_hrs == desired_hrs


# ===========================================================================
# Tests: Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_empty_edit_no_change(self, tmp_path: Path) -> None:
        """Editing text to the same value produces no change."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.",
            replace="Second plain paragraph.",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        assert body_texts(result.base.document) == body_texts(result.desired.document)

    def test_whitespace_only_edit(self, tmp_path: Path) -> None:
        """Adding blank lines doesn't create phantom paragraphs that break
        unrelated content."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        # Add extra blank lines between two paragraphs
        md = md.replace(
            "Second plain paragraph.\n",
            "Second plain paragraph.\n\n\n",
        )
        rt.write_md(md)
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)

    def test_multiple_edits_in_same_tab(self, tmp_path: Path) -> None:
        """Multiple edits in the same tab all take effect."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        md = md.replace("Second plain paragraph.", "EDIT_ONE")
        md = md.replace("Final paragraph of the document.", "EDIT_TWO")
        rt.write_md(md)
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        texts = body_texts(result.desired.document)
        assert "EDIT_ONE" in texts
        assert "EDIT_TWO" in texts
        assert "Second plain paragraph." not in texts
        assert "Final paragraph of the document." not in texts


# ===========================================================================
# Tests: Footnotes (added via markdown editing)
# ===========================================================================


class TestFootnotes:
    def test_add_footnote_via_markdown(self, tmp_path: Path) -> None:
        """User adds a footnote reference and definition in markdown."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        # Add footnote ref to a paragraph and definition at the end
        md = md.replace(
            "Second plain paragraph.",
            "Second plain paragraph[^fn1].",
        )
        md = md.rstrip() + "\n\n[^fn1]: This is a new footnote.\n"
        rt.write_md(md)
        result = rt.deserialize()
        assert_preserved(
            result.base.document,
            result.desired.document,
            skip_fields={"footnotes"},
        )
        # Check that the footnote exists in desired
        dt = _tab_dt(result.desired.document)
        footnotes = dt.footnotes or {}
        assert len(footnotes) > 0
        # Check the footnote content
        found = False
        for fn in footnotes.values():
            for se in fn.content or []:
                if se.paragraph:
                    text = "".join(
                        (pe.text_run.content or "")
                        for pe in (se.paragraph.elements or [])
                        if pe.text_run
                    )
                    if "new footnote" in text:
                        found = True
        assert found, "Footnote text not found in desired"

    def test_add_multiple_footnotes(self, tmp_path: Path) -> None:
        """User adds multiple footnote references and definitions."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        md = md.replace(
            "This is a plain paragraph with no formatting.",
            "This is a plain paragraph[^a] with no formatting[^b].",
        )
        md = md.rstrip() + "\n\n[^a]: First note.\n\n[^b]: Second note.\n"
        rt.write_md(md)
        result = rt.deserialize()
        assert_preserved(
            result.base.document,
            result.desired.document,
            skip_fields={"footnotes"},
        )
        dt = _tab_dt(result.desired.document)
        footnotes = dt.footnotes or {}
        assert len(footnotes) >= 2


# ===========================================================================
# Tests: Inline code
# ===========================================================================


class TestInlineCode:
    def test_add_inline_code(self, tmp_path: Path) -> None:
        """User adds inline code to a paragraph."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.",
            replace="Second `code_here` paragraph.",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        # Find the paragraph and check for Courier New font
        found_code = False
        for se in _body_content(result.desired.document):
            if not se.paragraph:
                continue
            for pe in se.paragraph.elements or []:
                if not pe.text_run:
                    continue
                if "code_here" in (pe.text_run.content or ""):
                    ts = pe.text_run.text_style
                    if (
                        ts
                        and ts.weighted_font_family
                        and ts.weighted_font_family.font_family == "Courier New"
                    ):
                        found_code = True
        assert found_code, "Expected Courier New font for inline code"


# ===========================================================================
# Tests: Thematic break (HR) via markdown
# ===========================================================================


class TestThematicBreak:
    def test_add_hr_via_markdown(self, tmp_path: Path) -> None:
        """User adds --- in markdown → produces HR element in desired."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Text near the end.\n",
            replace="Text near the end.\n\n---\n",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        # Check that an HR exists in desired
        found_hr = False
        for se in _body_content(result.desired.document):
            if se.paragraph:
                for pe in se.paragraph.elements or []:
                    if pe.horizontal_rule is not None:
                        found_hr = True
        assert found_hr, "Expected horizontal rule in desired"


# ===========================================================================
# Tests: Add/delete rows in existing tables
# ===========================================================================


class TestTableRowEdits:
    def test_add_table_row(self, tmp_path: Path) -> None:
        """Add a new row to an existing GFM table."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="| Beta | 200 | The second item |",
            replace="| Beta | 200 | The second item |\n| Delta | 400 | The fourth item |",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        assert len(tables) == 1
        assert len(tables[0]) == 4  # was 3, now 4
        assert tables[0][3] == ["Delta", "400", "The fourth item"]
        # Existing rows unchanged
        assert tables[0][0] == ["Name", "Value", "Description"]
        assert tables[0][1] == ["Alpha", "100", "The first item"]

    def test_delete_table_row(self, tmp_path: Path) -> None:
        """Delete a data row from an existing table."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        # Remove the Alpha row
        lines = md.splitlines(keepends=True)
        lines = [
            line for line in lines if "Alpha" not in line or "| Alpha |" not in line
        ]
        rt.write_md("".join(lines))
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        assert len(tables) == 1
        assert len(tables[0]) == 2  # header + Beta only
        assert tables[0][1][0] == "Beta"


# ===========================================================================
# Tests: Creating brand new tables from markdown
# ===========================================================================


class TestNewTableCreation:
    def test_create_simple_table(self, tmp_path: Path) -> None:
        """Create a brand new 2-column table from GFM markdown."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        new_table = (
            "| Col A | Col B |\n| --- | --- |\n| r1c1 | r1c2 |\n| r2c1 | r2c2 |\n"
        )
        rt.edit_md(
            find="Second plain paragraph.\n",
            replace="Second plain paragraph.\n\n" + new_table,
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        assert len(tables) == 2  # original + new
        # Find the new table (2 cols)
        new_tbl = [t for t in tables if len(t[0]) == 2]
        assert len(new_tbl) == 1
        assert new_tbl[0] == [
            ["Col A", "Col B"],
            ["r1c1", "r1c2"],
            ["r2c1", "r2c2"],
        ]
        # Original table still intact
        orig_tbl = [t for t in tables if len(t[0]) == 3]
        assert len(orig_tbl) == 1
        assert orig_tbl[0][0] == ["Name", "Value", "Description"]

    def test_create_large_table(self, tmp_path: Path) -> None:
        """Create a table with many rows and columns."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        header = "| A | B | C | D | E |"
        separator = "| --- | --- | --- | --- | --- |"
        rows = [f"| a{i} | b{i} | c{i} | d{i} | e{i} |" for i in range(1, 6)]
        new_table = "\n".join([header, separator, *rows]) + "\n"
        rt.edit_md(
            find="Second plain paragraph.\n",
            replace="Second plain paragraph.\n\n" + new_table,
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        dims = table_dimensions(result.desired.document)
        # Should have a 5-col table (6 rows = header + 5 data)
        assert (6, 5) in dims

    def test_create_table_with_empty_cells(self, tmp_path: Path) -> None:
        """Create a table where some cells are empty."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        new_table = "| H1 | H2 | H3 |\n| --- | --- | --- |\n| a |  | c |\n|  | b |  |\n"
        rt.edit_md(
            find="Second plain paragraph.\n",
            replace="Second plain paragraph.\n\n" + new_table,
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        # Find the new 3-col, 3-row table (not the original which is also 3-col)
        new_tbls = [t for t in tables if len(t) == 3 and t[0] == ["H1", "H2", "H3"]]
        assert len(new_tbls) == 1
        assert new_tbls[0][1] == ["a", "", "c"]
        assert new_tbls[0][2] == ["", "b", ""]

    def test_create_table_after_heading(self, tmp_path: Path) -> None:
        """Create a new table immediately after a heading."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        new_table = "| Key | Val |\n| --- | --- |\n| x | 1 |\n"
        rt.edit_md(
            find="# Second Major Section\n",
            replace="# Second Major Section\n\n" + new_table,
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        new_tbl = [t for t in tables if len(t[0]) == 2 and t[0] == ["Key", "Val"]]
        assert len(new_tbl) == 1
        assert new_tbl[0][1] == ["x", "1"]

    def test_create_single_row_table(self, tmp_path: Path) -> None:
        """Create a table with only a header row and one data row."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        new_table = "| Only |\n| --- |\n| single |\n"
        rt.edit_md(
            find="Second plain paragraph.\n",
            replace="Second plain paragraph.\n\n" + new_table,
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        single_col_tables = [t for t in tables if len(t[0]) == 1]
        assert len(single_col_tables) == 1
        assert single_col_tables[0] == [["Only"], ["single"]]


# ===========================================================================
# Tests: Table cell formatting (bold, italic, links)
# ===========================================================================


class TestTableCellFormatting:
    def test_bold_text_in_cell(self, tmp_path: Path) -> None:
        """Add bold formatting to a table cell."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="| Alpha |", replace="| **Alpha** |")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = table_cell_runs(result.desired.document, row=1, col=0)
        assert any(r["text"].strip() == "Alpha" and r["bold"] for r in runs)

    def test_italic_text_in_cell(self, tmp_path: Path) -> None:
        """Add italic formatting to a table cell."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(find="| Alpha |", replace="| *Alpha* |")
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = table_cell_runs(result.desired.document, row=1, col=0)
        assert any(r["text"].strip() == "Alpha" and r["italic"] for r in runs)

    def test_link_in_cell(self, tmp_path: Path) -> None:
        """Add a hyperlink to a table cell."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="| Alpha |",
            replace="| [Alpha](https://alpha.com) |",
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        runs = table_cell_runs(result.desired.document, row=1, col=0)
        assert any("Alpha" in r["text"] and "alpha.com" in r["link"] for r in runs)

    def test_new_table_with_bold_cells(self, tmp_path: Path) -> None:
        """Create a brand new table with bold text in cells."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        new_table = (
            "| Item | Status |\n"
            "| --- | --- |\n"
            "| Task A | **Done** |\n"
            "| Task B | Pending |\n"
        )
        rt.edit_md(
            find="Second plain paragraph.\n",
            replace="Second plain paragraph.\n\n" + new_table,
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        new_tbls = [t for t in tables if len(t[0]) == 2 and t[0] == ["Item", "Status"]]
        assert len(new_tbls) == 1
        # Find the new table index
        all_tables = table_cell_texts(result.desired.document)
        for ti, tbl in enumerate(all_tables):
            if tbl[0] == ["Item", "Status"]:
                runs = table_cell_runs(
                    result.desired.document, table_idx=ti, row=1, col=1
                )
                assert any(r["text"].strip() == "Done" and r["bold"] for r in runs)
                break

    def test_new_table_with_links(self, tmp_path: Path) -> None:
        """Create a brand new table with links in cells."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        new_table = (
            "| Site | URL |\n"
            "| --- | --- |\n"
            "| [Example](https://example.com) | Production |\n"
        )
        rt.edit_md(
            find="Second plain paragraph.\n",
            replace="Second plain paragraph.\n\n" + new_table,
        )
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        all_tables = table_cell_texts(result.desired.document)
        for ti, tbl in enumerate(all_tables):
            if len(tbl[0]) == 2 and tbl[0] == ["Site", "URL"]:
                runs = table_cell_runs(
                    result.desired.document, table_idx=ti, row=1, col=0
                )
                assert any("example.com" in r["link"] for r in runs)
                break
        else:
            pytest.fail("New table with links not found")


# ===========================================================================
# Tests: Table deletion
# ===========================================================================


class TestTableDeletion:
    def test_delete_table(self, tmp_path: Path) -> None:
        """Delete an entire table from markdown."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        # Remove the entire GFM table (header + separator + data rows)
        md = re.sub(
            r"\| Name \|.*?\| Beta \| 200 \| The second item \|\n",
            "",
            md,
            flags=re.DOTALL,
        )
        rt.write_md(md)
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        tables = table_cell_texts(result.desired.document)
        assert len(tables) == 0

    def test_delete_table_preserves_surrounding_content(self, tmp_path: Path) -> None:
        """Deleting a table doesn't affect paragraphs before/after it."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        md = rt.read_md()
        md = re.sub(
            r"\| Name \|.*?\| Beta \| 200 \| The second item \|\n",
            "",
            md,
            flags=re.DOTALL,
        )
        rt.write_md(md)
        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        texts = body_texts(result.desired.document)
        # Content before and after the table should survive
        assert "Deep nested heading content." in texts
        assert "Text near the end." in texts
        assert "Final paragraph of the document." in texts


# ===========================================================================
# Tests: Heading ID preservation
# ===========================================================================


class TestHeadingIds:
    def test_heading_id_preserved_on_noop(self, tmp_path: Path) -> None:
        """Heading IDs survive when heading text is NOT edited."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        # Get the base heading ID for "Introduction"
        base_heading_id = None
        for se in _body_content(rt.bundle.document):
            if se.paragraph and se.paragraph.paragraph_style:
                ps = se.paragraph.paragraph_style
                if ps.named_style_type and "HEADING" in str(ps.named_style_type):
                    text = "".join(
                        (pe.text_run.content or "").rstrip("\n")
                        for pe in (se.paragraph.elements or [])
                        if pe.text_run
                    )
                    if text == "Introduction":
                        base_heading_id = ps.heading_id
                        break

        assert base_heading_id is not None

        # No edits to the heading
        result = rt.deserialize()

        desired_heading_id = None
        for se in _body_content(result.desired.document):
            if se.paragraph and se.paragraph.paragraph_style:
                ps = se.paragraph.paragraph_style
                text = "".join(
                    (pe.text_run.content or "").rstrip("\n")
                    for pe in (se.paragraph.elements or [])
                    if pe.text_run
                )
                if text == "Introduction":
                    desired_heading_id = ps.heading_id
                    break
        assert desired_heading_id == base_heading_id


# ===========================================================================
# Tests: Comments handling
# ===========================================================================


class TestCommentsHandling:
    def test_comments_from_edited_folder(self, tmp_path: Path) -> None:
        """Desired uses comments from the edited folder, not from base."""
        from extradoc.comments._types import Comment
        from extradoc.comments._xml import to_xml as comments_to_xml

        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        # Write a custom comments.xml
        mine_comment = Comment(
            id="test-comment-1",
            author="tester@example.com",
            created_time="2024-06-01T00:00:00Z",
            content="This is a test comment",
            anchor="kix.test",
            resolved=False,
            deleted=False,
        )
        mine_comments = FileComments(file_id=MD_GOLDEN_ID, comments=[mine_comment])
        (rt.folder / "comments.xml").write_text(
            comments_to_xml(mine_comments), encoding="utf-8"
        )

        result = rt.deserialize()
        assert_preserved(result.base.document, result.desired.document)
        comment_ids = [c.id for c in result.desired.comments.comments]
        assert "test-comment-1" in comment_ids

    def test_resolved_comment(self, tmp_path: Path) -> None:
        """Resolving a comment in comments.xml is reflected in desired."""
        from extradoc.comments._types import Comment
        from extradoc.comments._xml import to_xml as comments_to_xml

        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        comment = Comment(
            id="resolve-me",
            author="tester@example.com",
            created_time="2024-01-01T00:00:00Z",
            content="Resolve this",
            anchor="kix.abc",
            resolved=True,
            deleted=False,
        )
        mine_comments = FileComments(file_id=MD_GOLDEN_ID, comments=[comment])
        (rt.folder / "comments.xml").write_text(
            comments_to_xml(mine_comments), encoding="utf-8"
        )

        result = rt.deserialize()
        resolved = [c for c in result.desired.comments.comments if c.resolved]
        assert any(c.id == "resolve-me" for c in resolved)


# ===========================================================================
# Tests: Body content count preservation on no-op
# ===========================================================================


class TestBodyContentPreservation:
    def test_structural_element_count_preserved(self, tmp_path: Path) -> None:
        """No-op round-trip preserves the number of structural elements."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        base_count = len(_body_content(result.base.document))
        desired_count = len(_body_content(result.desired.document))
        assert base_count == desired_count, (
            f"SE count changed: {base_count} → {desired_count}"
        )

    def test_table_content_preserved(self, tmp_path: Path) -> None:
        """No-op round-trip preserves exact table content."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        base_tables = table_cell_texts(result.base.document)
        desired_tables = table_cell_texts(result.desired.document)
        assert base_tables == desired_tables
        # Also verify dimensions
        assert table_dimensions(result.base.document) == table_dimensions(
            result.desired.document
        )

    def test_list_items_preserved(self, tmp_path: Path) -> None:
        """No-op round-trip preserves exact list item text and count."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        result = rt.deserialize()
        base_items = body_list_items(result.base.document)
        desired_items = body_list_items(result.desired.document)
        assert len(base_items) == len(desired_items)
        for bi, di in zip(base_items, desired_items, strict=True):
            assert bi["text"] == di["text"]
