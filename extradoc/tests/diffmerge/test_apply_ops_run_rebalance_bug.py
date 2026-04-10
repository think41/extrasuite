"""Regression test for ``_merge_changed_paragraph`` run rebalancing.

Bug (part 2 of the FORM-15G QA finding):

When the markdown serde merges a user edit back into the base Document, the
3-way merge in ``_merge_changed_paragraph`` walks the desired paragraph's
runs using offset-based style lookup. If the desired paragraph carries stale
run splits (e.g. the markdown deserializer kept the base run boundary at the
same character position even though characters were inserted earlier in the
paragraph), the merged paragraph ends up with the wrong run boundaries —
e.g. the ``s`` of ``Status`` becomes superscript instead of the ``4``.

Base paragraph runs:
    ``"ResidentialStatus"`` NONE (17 chars)
    ``"4"`` SUPERSCRIPT (1 char)
    ``"\n"`` NONE

Desired paragraph text: ``"Residential Status4\n"`` (one space inserted at
offset 11). The correct merged runs must be:

    ``"Residential Status"`` NONE (18 chars)
    ``"4"`` SUPERSCRIPT (1 char)
    ``"\n"`` NONE

With the bug, the merged paragraph groups the superscript boundary at the
base run's original offset (17), so ``"s"`` ends up superscripted.

The ancestor (pre-edit) matches the base exactly. The desired paragraph is
reconstructed from markdown with a SINGLE text run (markdown lost the
superscript styling) covering all 20 chars. ``_merge_changed_paragraph``
must split this single desired run at the correct content-relative offset
so the superscript styling lands on ``4``.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    StructuralElement,
    TextRun,
)
from extradoc.diffmerge.apply_ops import _merge_changed_paragraph


def _text_run_dict(content: str, bold: bool = False, superscript: bool = False) -> dict:
    ts: dict = {}
    if bold:
        ts["bold"] = True
    if superscript:
        ts["baselineOffset"] = "SUPERSCRIPT"
    return {"textRun": {"content": content, "textStyle": ts}}


def _ancestor_element(text: str) -> StructuralElement:
    """Build an ancestor element with a single run covering ``text + '\\n'``."""
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


def _desired_element(text: str) -> StructuralElement:
    """Build a desired (post-edit) element with a single run — what markdown
    deserialize produces when the style can't be represented in markdown.
    """
    return _ancestor_element(text)


def test_merge_preserves_superscript_on_correct_character_after_space_insert() -> None:
    """Inserting ``" "`` into ``ResidentialStatus4`` must keep ``4`` superscripted.

    The merged paragraph's runs must be:
        NONE "Residential Status" (18 chars)
        SUPERSCRIPT "4" (1 char)
        NONE "\n"

    Without the fix the superscript boundary stays at its original char
    offset (17), landing on the ``s`` of ``Status`` instead of the ``4``.
    """
    raw_base = {
        "paragraph": {
            "elements": [
                _text_run_dict("ResidentialStatus"),  # 17 chars NONE
                _text_run_dict("4", superscript=True),  # 1 char SUPER
                _text_run_dict("\n"),  # terminator NONE
            ],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        }
    }

    # Ancestor matches base text (before the user edit).
    ancestor = _ancestor_element("ResidentialStatus4")
    # Desired from markdown: single run, space inserted.
    desired = _desired_element("Residential Status4")

    merged = _merge_changed_paragraph(raw_base, desired, ancestor_el=ancestor)

    runs = merged["paragraph"]["elements"]
    # Extract (content, baselineOffset) pairs for visible runs.
    pairs = []
    for r in runs:
        tr = r.get("textRun")
        if tr is None:
            continue
        ts = tr.get("textStyle") or {}
        pairs.append((tr.get("content", ""), ts.get("baselineOffset")))

    # Reconstruct full text
    full_text = "".join(c for c, _ in pairs)
    assert full_text == "Residential Status4\n", f"merged text mismatch: {full_text!r}"

    # Find which characters are superscripted.
    super_chars: list[str] = []
    for content, baseline in pairs:
        if baseline == "SUPERSCRIPT":
            super_chars.append(content)

    assert super_chars == ["4"], (
        "superscript leaked to wrong character(s). "
        f"expected ['4'], got {super_chars!r}. "
        f"full run structure: {pairs!r}"
    )
