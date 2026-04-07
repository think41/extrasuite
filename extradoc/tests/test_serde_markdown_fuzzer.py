"""Fuzzer test for MarkdownSerde: single-word edits should not cascade.

This test:
1. Loads the OASIS CIQ golden document
2. Serializes to markdown
3. Picks random words from the markdown and replaces them one at a time
4. Deserializes and runs reconcile
5. Asserts the batchUpdate request count is small (<=3)

A single word replacement should produce a minimal set of API requests.
If it produces many, something in the serde round-trip is generating
spurious diffs.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.serde.markdown import MarkdownSerde

GOLDEN_DIR = Path(__file__).parent / "golden"
OASIS_CIQ_ID = "19GeM80fb9c0uHEget4jaR8WotgXwNpTwTaOHzynH-PI"

_serde = MarkdownSerde()


def _load_golden(doc_id: str) -> Document:
    path = GOLDEN_DIR / f"{doc_id}.json"
    return Document.model_validate(json.loads(path.read_text()))


def _make_bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


def _count_requests(batches) -> int:
    """Count total number of individual requests across all batches."""
    total = 0
    for batch in batches:
        if batch.requests:
            total += len(batch.requests)
    return total


def _find_replaceable_words(md_text: str) -> list[tuple[str, int]]:
    """Find words in the markdown that are safe to replace.

    Returns (word, position) tuples. Skips:
    - Words inside URLs, links, HTML tags
    - Very short words (< 4 chars)
    - Markdown syntax characters
    """
    words = []
    # Find words that are plain text (not in URLs, tags, etc.)
    for m in re.finditer(r'(?<![<\[(=/])([A-Za-z]{4,})', md_text):
        word = m.group(1)
        pos = m.start(1)
        # Skip if inside a URL or HTML tag
        line_start = md_text.rfind('\n', 0, pos)
        line = md_text[line_start:md_text.find('\n', pos)]
        if 'http' in line and pos > line.find('http') + line_start:
            continue
        if '<' in md_text[max(0, pos - 50):pos] and '>' not in md_text[max(0, pos - 50):pos]:
            continue
        words.append((word, pos))
    return words


def _do_single_word_edit(
    doc_id: str, tmp_path: Path, word_idx: int, seed: int = 42
) -> tuple[str, str, int]:
    """Serialize, replace one word, deserialize, reconcile.

    Returns (original_word, replacement, request_count).
    """
    doc = _load_golden(doc_id)
    bundle = _make_bundle(doc)
    folder = tmp_path / f"edit_{word_idx}"
    _serde.serialize(bundle, folder)

    md_path = folder / "Tab_1.md"
    md_text = md_path.read_text(encoding="utf-8")

    replaceable = _find_replaceable_words(md_text)
    assert replaceable, "No replaceable words found"

    rng = random.Random(seed + word_idx)
    orig_word, pos = replaceable[word_idx % len(replaceable)]
    replacement = f"FUZZ{rng.randint(1000, 9999)}"

    # Replace only the specific occurrence at this position
    new_text = md_text[:pos] + replacement + md_text[pos + len(orig_word):]
    md_path.write_text(new_text, encoding="utf-8")

    result = _serde.deserialize(folder)
    base_doc = result.base.document
    desired_doc = result.desired.document

    batches = reconcile_batches(base_doc, desired_doc)
    req_count = _count_requests(batches)

    return orig_word, replacement, req_count


# Use a fixed set of word indices spread across the document
WORD_INDICES = [0, 10, 25, 50, 100, 150, 200, 300, 400, 500]


@pytest.mark.parametrize("word_idx", WORD_INDICES)
def test_single_word_edit_minimal_requests(tmp_path: Path, word_idx: int):
    """A single word replacement should produce at most 3 API requests."""
    orig, repl, req_count = _do_single_word_edit(OASIS_CIQ_ID, tmp_path, word_idx)
    assert req_count <= 3, (
        f"Replacing '{orig}' with '{repl}' generated {req_count} requests "
        f"(expected <= 3). This suggests spurious diffs in the serde round-trip."
    )


def test_no_edit_zero_requests(tmp_path: Path):
    """Serialize then deserialize with NO edits should produce 0 requests."""
    doc = _load_golden(OASIS_CIQ_ID)
    bundle = _make_bundle(doc)
    folder = tmp_path / "no_edit"
    _serde.serialize(bundle, folder)

    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    req_count = _count_requests(batches)

    assert req_count == 0, (
        f"No-edit round-trip produced {req_count} requests. "
        f"Serde is not preserving document structure faithfully."
    )
