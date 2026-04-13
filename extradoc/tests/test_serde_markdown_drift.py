"""Drift xfail tests: push → repull convergence for formatting and footnotes.

Each test simulates a full push→repull cycle using the mock API:
  1. Build a synthetic base document with specific formatting.
  2. Serialize to markdown (= what the LLM sees after pull).
  3. Make a targeted edit (or no edit for noop tests).
  4. Deserialize to produce (base, desired) via 3-way merge.
  5. Reconcile base→desired to get batchUpdate requests.
  6. Apply the batches to MockGoogleDocsAPI (starting from the reindexed base).
  7. Re-serialize the mock result (= what a re-pull returns).
  8. Assert: re-serialized content == pushed content (no drift).

Assertion discipline: every assertion names the EXACT characters / lines that
drifted and WHY that constitutes a real bug.

All 12 tests pass (no xfail).

Bug A — mock/text_ops.py: ``_delete_content_from_segment`` now preserves
non-textRun elements (footnoteReference, etc.) that lie outside the delete
range.  ``_insert_into_paragraph`` now handles insertText at a position
occupied by a non-textRun element by inserting a new textRun before it.

Bug B — serde/markdown/_from_markdown.py: footnote definitions are stripped
from the source before passing to mistletoe, preventing mistletoe from
treating ``[^fn1]: text`` as a GFM link-reference definition.

Bug C (reconciler) — reconcile_v3/lower.py: ``_inherited_insert_style`` now
accepts a ``delete_end`` parameter for the replace case.  The right-neighbour
style is computed starting from ``delete_end``, not ``base_pos``, so deleted
characters are not mistakenly treated as the inherited style context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from extradoc.api_types._generated import (
    Body,
    Document,
    DocumentTab,
    Footnote,
    FootnoteReference,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    SectionBreak,
    SectionStyle,
    StructuralElement,
    Tab,
    TabProperties,
    TextRun,
    TextStyle,
    WeightedFontFamily,
)
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.serde.markdown import MarkdownSerde

_serde = MarkdownSerde()


# ---------------------------------------------------------------------------
# Document / paragraph builders
# ---------------------------------------------------------------------------


def _para(
    elements: list[ParagraphElement],
    named_style: str = "NORMAL_TEXT",
) -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=elements,
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        )
    )


def _text_run(text: str, **style_kwargs: Any) -> ParagraphElement:
    ts = TextStyle(**style_kwargs) if style_kwargs else TextStyle()
    return ParagraphElement(text_run=TextRun(content=text, text_style=ts))


def _inline_code_run(text: str) -> ParagraphElement:
    """Return a ParagraphElement styled as inline code (Courier New)."""
    return ParagraphElement(
        text_run=TextRun(
            content=text,
            text_style=TextStyle(
                weighted_font_family=WeightedFontFamily(font_family="Courier New")
            ),
        )
    )


def _footnote_ref(fn_id: str) -> ParagraphElement:
    return ParagraphElement(footnote_reference=FootnoteReference(footnote_id=fn_id))


def _make_doc(
    paras: list[StructuralElement],
    footnotes: dict[str, Footnote] | None = None,
    doc_id: str = "doc1",
) -> Document:
    """Wrap body paragraphs in a minimal multi-tab Document."""
    body_content: list[StructuralElement] = [
        StructuralElement(section_break=SectionBreak(section_style=SectionStyle())),
        *paras,
    ]
    dt = DocumentTab(
        body=Body(content=body_content),
        footnotes=footnotes or {},
    )
    tab = Tab(
        tab_properties=TabProperties(tab_id="t.0", title="Tab 1", index=0),
        document_tab=dt,
    )
    return Document(document_id=doc_id, tabs=[tab])


def _reindex(doc: Document) -> Document:
    """Assign concrete startIndex/endIndex via the mock's reindex pass."""
    from extradoc.mock.reindex import reindex_and_normalize_all_tabs

    d = doc.model_dump(by_alias=True, exclude_none=True)
    reindex_and_normalize_all_tabs(d)
    return Document.model_validate(d)


def _bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or "doc1"),
    )


def _tab_file(folder: Path, tab: str = "Tab_1") -> Path:
    new = folder / "tabs" / f"{tab}.md"
    if new.exists():
        return new
    legacy = folder / f"{tab}.md"
    if legacy.exists():
        return legacy
    return new


def _strip_frontmatter(md: str) -> str:
    """Remove YAML front-matter (--- ... ---) so content comparisons are stable."""
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[end + 4 :].lstrip("\n")
    return md


def _simple_footnote(fn_id: str, body_text: str) -> Footnote:
    return Footnote(
        footnote_id=fn_id,
        content=[
            StructuralElement(
                paragraph=Paragraph(
                    elements=[_text_run(body_text + "\n")],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                )
            ),
            StructuralElement(
                paragraph=Paragraph(
                    elements=[_text_run("\n")],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                )
            ),
        ],
    )


def _push_repull(
    base_doc: Document,
    edited_md: str,
    tmp_path: Path,
) -> tuple[str, str]:
    """Full push→repull cycle using MockGoogleDocsAPI.

    Returns (pushed_content, repull_content) — both with frontmatter stripped.
    """
    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    tf.write_text(edited_md, encoding="utf-8")

    result = _serde.deserialize(folder)
    base = result.base.document
    desired = result.desired.document

    batches = reconcile_batches(base, desired)
    mock = MockGoogleDocsAPI(base_doc)
    for batch in batches:
        mock.batch_update(batch)

    repull_doc = mock.get()
    repull_folder = tmp_path / "repull"
    _serde.serialize(_bundle(repull_doc), repull_folder)

    pushed_content = _strip_frontmatter(edited_md)
    repull_md = _tab_file(repull_folder).read_text(encoding="utf-8")
    repull_content = _strip_frontmatter(repull_md)

    return pushed_content, repull_content


# ===========================================================================
# Noop round-trips — working correctly (no xfail)
# ===========================================================================


def test_noop_footnote_ref_produces_empty_diff(tmp_path: Path) -> None:
    """Noop: paragraph with footnote reference → reconcile must produce 0 batches."""
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("Before text"),
                        _footnote_ref("fn1"),
                        _text_run(" after text\n"),
                    ]
                )
            ],
            footnotes={"fn1": _simple_footnote("fn1", "Footnote body text.")},
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    total_requests = sum(len(b.requests or []) for b in batches)

    assert total_requests == 0, (
        f"Noop round-trip with footnote produced {total_requests} reconcile request(s). "
        f"Expected 0.\nBatches: {batches}"
    )


def test_noop_inline_code_produces_empty_diff(tmp_path: Path) -> None:
    """Noop: paragraph with inline code → reconcile must produce 0 batches."""
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("prefix "),
                        _text_run("bold", bold=True),
                        _text_run(" "),
                        _inline_code_run("code"),
                        _text_run(" suffix\n"),
                    ]
                )
            ]
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    total_requests = sum(len(b.requests or []) for b in batches)

    assert total_requests == 0, (
        f"Noop round-trip with inline code produced {total_requests} request(s). "
        f"Expected 0.\nBatches: {batches}"
    )


def test_noop_bold_underline_combo_produces_empty_diff(tmp_path: Path) -> None:
    """Noop: bold+underline combo → reconcile must produce 0 batches."""
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("TERM", bold=True, underline=True),
                        _text_run(". Normal text.\n"),
                    ]
                )
            ]
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    total_requests = sum(len(b.requests or []) for b in batches)

    assert total_requests == 0, (
        f"Noop round-trip with bold+underline produced {total_requests} request(s). "
        f"Expected 0.\nBatches: {batches}"
    )


def test_noop_multiple_footnote_refs_produces_empty_diff(tmp_path: Path) -> None:
    """Noop: two footnote refs in one paragraph → 0 batches."""
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("text"),
                        _footnote_ref("fn1"),
                        _text_run(" middle"),
                        _footnote_ref("fn2"),
                        _text_run(" end\n"),
                    ]
                )
            ],
            footnotes={
                "fn1": _simple_footnote("fn1", "First footnote."),
                "fn2": _simple_footnote("fn2", "Second footnote."),
            },
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    total_requests = sum(len(b.requests or []) for b in batches)

    assert total_requests == 0, (
        f"Noop round-trip with two footnote refs produced {total_requests} request(s). "
        f"Expected 0.\nBatches: {batches}"
    )


def test_footnote_content_edit_survives_repull(tmp_path: Path) -> None:
    """Edit footnote definition text; repull must show the new footnote text."""
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("Main body text"),
                        _footnote_ref("fn1"),
                        _text_run(" continues.\n"),
                    ]
                )
            ],
            footnotes={"fn1": _simple_footnote("fn1", "Original footnote content.")},
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "[^fn1]: Original footnote content." in md

    edited_md = md.replace(
        "[^fn1]: Original footnote content.",
        "[^fn1]: Updated footnote content.",
    )
    tf.write_text(edited_md, encoding="utf-8")

    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)

    assert "[^fn1]: Updated footnote content." in repull, (
        f"Updated footnote content not present in repull.\n"
        f"Pushed:\n{pushed}\nRepull:\n{repull}"
    )
    assert "[^fn1]: Original footnote content." not in repull
    assert "Main body text" in repull


# Formatting boundary edits — working correctly (no xfail)


def test_fmt_edit_before_bold_repull_matches_push(tmp_path: Path) -> None:
    """Edit 'prefix ' → 'REPLACED ' in 'prefix **bold**'; repull must match."""
    base_doc = _reindex(
        _make_doc(
            [_para([_text_run("prefix "), _text_run("bold", bold=True), _text_run("\n")])]
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "**bold**" in md

    edited_md = md.replace("prefix ", "REPLACED ")
    tf.write_text(edited_md, encoding="utf-8")
    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)

    assert "**bold**" in repull, (
        f"Bold boundary drifted after editing plain text before it.\n"
        f"Pushed:\n{pushed}\nRepull:\n{repull}"
    )
    assert _strip_frontmatter(pushed) == repull


def test_fmt_edit_after_bold_repull_matches_push(tmp_path: Path) -> None:
    """Edit ' suffix' → ' SUFFIX' in '**bold** suffix'; repull must match."""
    base_doc = _reindex(
        _make_doc([_para([_text_run("bold", bold=True), _text_run(" suffix\n")])])
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "**bold**" in md

    edited_md = md.replace(" suffix", " SUFFIX")
    tf.write_text(edited_md, encoding="utf-8")
    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)

    assert "**bold**" in repull
    assert "SUFFIX" in repull
    assert _strip_frontmatter(pushed) == repull


def test_code_edit_before_inline_code_repull_matches_push(tmp_path: Path) -> None:
    """Edit 'run ' → 'RUN ' in 'run `code` here'; repull must match pushed."""
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("run "),
                        _inline_code_run("code"),
                        _text_run(" here\n"),
                    ]
                )
            ]
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "`code`" in md

    edited_md = md.replace("run ", "RUN ")
    tf.write_text(edited_md, encoding="utf-8")
    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)

    assert "`code`" in repull
    assert "RUN" in repull
    assert _strip_frontmatter(pushed) == repull


def test_combo_bold_underline_edit_suffix_repull_matches_push(tmp_path: Path) -> None:
    """Edit '. Normal text.' after '**<u>TERM</u>**'; repull must match."""
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("TERM", bold=True, underline=True),
                        _text_run(". Normal text.\n"),
                    ]
                )
            ]
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "TERM" in md

    edited_md = md.replace(". Normal text.", ". EDITED text.")
    tf.write_text(edited_md, encoding="utf-8")
    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)

    assert "TERM" in repull
    assert "EDITED" in repull
    assert _strip_frontmatter(pushed) == repull


# ===========================================================================
# Bug A: mock/text_ops.py drops non-textRun elements during partial delete
# ===========================================================================


def test_fn_edit_text_before_ref_footnote_ref_survives(tmp_path: Path) -> None:
    """Edit 'Before' → 'BEFORE'; fn_ref at index 7 must survive delete [2,7).

    Bug A trace:
      Base: 'B'[1] 'efore'[2,7) fn_ref[7,8) ' after\\n'[8,15)
      deleteContentRange [2,7): removes 'efore'; fn_ref at 7 is outside range.
      Mock incorrectly drops fn_ref (skips non-textRun in rebuild loop).
      insertText at 2 'EFORE': produces 'BEFORE after' (no fn_ref).
      Expected: 'BEFORE[^fn1] after'.
    """
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("Before"),
                        _footnote_ref("fn1"),
                        _text_run(" after\n"),
                    ]
                )
            ],
            footnotes={"fn1": _simple_footnote("fn1", "Footnote detail.")},
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "[^fn1]" in md, f"fn_ref not in serialized markdown:\n{md}"

    edited_md = md.replace("Before", "BEFORE")
    tf.write_text(edited_md, encoding="utf-8")
    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)

    # Primary assertion: fn_ref must be present in repull
    assert "[^fn1]" in repull, (
        f"Bug A: fn_ref [^fn1] was DROPPED from repull after editing text before it.  "
        f"The mock's deleteContentRange [2,7) deleted fn_ref at [7,8) even though "
        f"fn_ref's startIndex=7 equals endIndex=7 of the delete range (exclusive).  "
        f"Root cause: _delete_content_from_segment skips non-textRun elements "
        f"unconditionally, so fn_ref is never added to 'surviving_runs'.\n"
        f"Pushed:\n{pushed}\nRepull:\n{repull}"
    )
    # Secondary: ensure the text edit actually took effect
    assert "BEFORE" in repull, (
        f"Edit 'Before'→'BEFORE' not reflected in repull.\n"
        f"Pushed:\n{pushed}\nRepull:\n{repull}"
    )
    # Tertiary: full round-trip equality
    assert _strip_frontmatter(pushed) == repull, (
        f"Full content mismatch after push+repull (edit-before-footnote scenario).\n"
        f"--- pushed ---\n{_strip_frontmatter(pushed)}\n--- repull ---\n{repull}"
    )


# ===========================================================================
# Bug B: _from_markdown.py parses [^fn1] as a Link when fn defs are present
# ===========================================================================


def test_fn_edit_text_after_ref_desired_doc_has_correct_structure(
    tmp_path: Path,
) -> None:
    """Desired doc after editing ' after'→' AFTER' must contain only one fn_ref.

    Bug B trace:
      Markdown after edit: 'word[^fn1] AFTER\\n\\n[^fn1]: Detail.'
      Mistletoe parses '[^fn1]: Detail.' as link-reference definition.
      Inline '[^fn1]' becomes Link('^fn1', url='Detail.').
      Desired paragraph elements:
        textRun('word') + textRun('^fn1', link='Detail.') + textRun(' AFTER')
        + footnoteReference('fn1') + textRun('\\n')    ← double fn_ref
      Reconcile sees the wrong desired structure and emits:
        deleteContentRange [6,12), insertText at 5 '^fn1 AFTER',
        updateTextStyle [5,9) link='Detail.'
      Repull shows: 'word[^fn1](Detail.) AFTER' (link applied to fn ref text).
    """
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("word"),
                        _footnote_ref("fn1"),
                        _text_run(" after\n"),
                    ]
                )
            ],
            footnotes={"fn1": _simple_footnote("fn1", "Detail.")},
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "[^fn1]" in md

    edited_md = md.replace(" after", " AFTER")
    tf.write_text(edited_md, encoding="utf-8")

    # Check the desired document structure directly — this is where Bug B is visible.
    result = _serde.deserialize(folder)
    desired_body = (
        result.desired.document.tabs[0].document_tab.body.content  # type: ignore[index]
        if result.desired.document.tabs
        else []
    )
    desired_paras = [se for se in (desired_body or []) if se.paragraph]
    assert desired_paras, "No paragraphs in desired document"

    para_elements = desired_paras[0].paragraph.elements or []

    # Count FootnoteReference elements in the paragraph
    fn_ref_elements = [pe for pe in para_elements if pe.footnote_reference is not None]
    # Count textRun elements that have a link style (the wrong "^fn1" textRun)
    link_text_runs = [
        pe
        for pe in para_elements
        if pe.text_run is not None
        and pe.text_run.text_style is not None
        and pe.text_run.text_style.link is not None
    ]

    assert len(fn_ref_elements) == 1, (
        f"Bug B: expected exactly 1 FootnoteReference in desired paragraph, "
        f"got {len(fn_ref_elements)}.  "
        f"When there are 2, one is the correct fn_ref and the other is the duplicate "
        f"created because mistletoe consumed '[^fn1]' as a Link token AND "
        f"_raw_text_with_footnote_refs also produced a fn_ref — double-processing.\n"
        f"Para elements: {[pe.model_dump(exclude_none=True) for pe in para_elements]}"
    )
    assert len(link_text_runs) == 0, (
        f"Bug B: found {len(link_text_runs)} textRun(s) with link style in the desired "
        f"paragraph — these are the wrong 'textRun({{content:\"^fn1\", link:{{url:\"Detail.\"}}}}' "
        f"elements produced because mistletoe parsed '[^fn1]' as a link reference.  "
        f"The link URL is the footnote BODY text (e.g. 'Detail.'), not a real URL.\n"
        f"Wrong runs: {[pe.model_dump(exclude_none=True) for pe in link_text_runs]}"
    )

    # Full push→repull equality
    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)
    assert _strip_frontmatter(pushed) == repull, (
        f"Full content mismatch after push+repull (edit-after-footnote).\n"
        f"--- pushed ---\n{_strip_frontmatter(pushed)}\n--- repull ---\n{repull}"
    )


def test_combo_bold_footnote_edit_desired_doc_has_no_link_runs(
    tmp_path: Path,
) -> None:
    """Edit bold 'important'→'IMPORTANT' in '**important**[^fn1] note'; desired must be clean.

    Desired paragraph must have:
      textRun('IMPORTANT', bold) + footnoteReference('fn1') + textRun(' note\\n')
    NOT:
      textRun('IMPORTANT', bold) + textRun('^fn1', link='See section 3.')
      + textRun(' note') + footnoteReference('fn1') + textRun('\\n')
    """
    base_doc = _reindex(
        _make_doc(
            [
                _para(
                    [
                        _text_run("important", bold=True),
                        _footnote_ref("fn1"),
                        _text_run(" note\n"),
                    ]
                )
            ],
            footnotes={"fn1": _simple_footnote("fn1", "See section 3.")},
        )
    )

    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)
    tf = _tab_file(folder)
    md = tf.read_text()
    assert "[^fn1]" in md

    edited_md = md.replace("important", "IMPORTANT")
    tf.write_text(edited_md, encoding="utf-8")

    result = _serde.deserialize(folder)
    desired_body = (
        result.desired.document.tabs[0].document_tab.body.content  # type: ignore[index]
        if result.desired.document.tabs
        else []
    )
    desired_paras = [se for se in (desired_body or []) if se.paragraph]
    assert desired_paras

    para_elements = desired_paras[0].paragraph.elements or []
    fn_ref_elements = [pe for pe in para_elements if pe.footnote_reference is not None]
    link_text_runs = [
        pe
        for pe in para_elements
        if pe.text_run is not None
        and pe.text_run.text_style is not None
        and pe.text_run.text_style.link is not None
    ]

    assert len(fn_ref_elements) == 1, (
        f"Bug B: expected 1 FootnoteReference in desired, got {len(fn_ref_elements)}.  "
        f"Double-processing of '[^fn1]' (mistletoe Link + _raw_text_with_footnote_refs).\n"
        f"Para elements: {[pe.model_dump(exclude_none=True) for pe in para_elements]}"
    )
    assert len(link_text_runs) == 0, (
        f"Bug B: found {len(link_text_runs)} textRun(s) with unexpected link style.  "
        f"These are the wrong '^fn1' textRuns created by the link-reference parsing bug.\n"
        f"Runs: {[pe.model_dump(exclude_none=True) for pe in link_text_runs]}"
    )

    pushed, repull = _push_repull(base_doc, edited_md, tmp_path)
    assert _strip_frontmatter(pushed) == repull, (
        f"Full content mismatch (bold+footnote combo).\n"
        f"--- pushed ---\n{_strip_frontmatter(pushed)}\n--- repull ---\n{repull}"
    )
