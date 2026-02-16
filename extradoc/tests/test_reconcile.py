"""Tests for the reconcile module - Phase 1: paragraph text in body."""

from extradoc.api_types._generated import Document
from extradoc.reconcile import reconcile, reindex_document, verify


def _make_doc(*paragraphs: str, tab_id: str = "t.0") -> Document:
    """Helper: create a Document with paragraphs in a single tab body.

    Each string becomes a paragraph. A trailing \\n is added if not present.
    A section break is prepended automatically.
    """
    content: list[dict] = [{"sectionBreak": {}}]
    for text in paragraphs:
        if not text.endswith("\n"):
            text = text + "\n"
        content.append({"paragraph": {"elements": [{"textRun": {"content": text}}]}})

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )
    return reindex_document(doc)


class TestReindexDocument:
    def test_basic_reindex(self):
        doc = _make_doc("Hello")
        tab = doc.tabs[0]
        body = tab.document_tab.body
        assert body.content is not None
        # Section break at index 0
        sb = body.content[0]
        assert sb.section_break is not None
        # Section break startIndex is None (first element has no startIndex)
        assert sb.start_index is None
        assert sb.end_index == 1
        # Paragraph "Hello\n" at index 1-7
        para = body.content[1]
        assert para.paragraph is not None
        assert para.start_index == 1
        assert para.end_index == 7  # "Hello\n" = 6 chars

    def test_multiple_paragraphs(self):
        doc = _make_doc("Hello", "World")
        body = doc.tabs[0].document_tab.body
        assert len(body.content) == 3  # sectionBreak + 2 paragraphs
        p1 = body.content[1]
        p2 = body.content[2]
        assert p1.end_index == p2.start_index


class TestReconcileNoChange:
    def test_identical_documents(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        # No changes needed
        assert result.requests is None or len(result.requests) == 0
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileAddParagraph:
    def test_add_paragraph_at_end(self):
        base = _make_doc("Hello")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert result.requests is not None
        assert len(result.requests) > 0
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_paragraph_at_beginning(self):
        base = _make_doc("World")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_multiple_paragraphs(self):
        base = _make_doc("Hello")
        desired = _make_doc("Hello", "Beautiful", "World")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileDeleteParagraph:
    def test_delete_paragraph_at_end(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("Hello")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_paragraph_at_beginning(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("World")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_middle_paragraph(self):
        base = _make_doc("Hello", "Beautiful", "World")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileModifyParagraph:
    def test_replace_all_content(self):
        base = _make_doc("Hello")
        desired = _make_doc("Goodbye")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileReorderParagraphs:
    def test_swap_two_paragraphs(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("World", "Hello")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_reverse_three_paragraphs(self):
        base = _make_doc("A", "B", "C")
        desired = _make_doc("C", "B", "A")
        result = reconcile(base, desired)
        assert result.requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileEdgeCases:
    def test_empty_paragraph_to_content(self):
        """Replace empty paragraph with content."""
        base = _make_doc("")
        desired = _make_doc("Hello")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_content_to_empty_paragraph(self):
        """Replace content with empty paragraph."""
        base = _make_doc("Hello")
        desired = _make_doc("")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_all_but_one(self):
        """Delete all paragraphs except the last one."""
        base = _make_doc("A", "B", "C", "D")
        desired = _make_doc("D")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_many_paragraphs(self):
        """Add several paragraphs at once."""
        base = _make_doc("Start")
        desired = _make_doc("Start", "Line 1", "Line 2", "Line 3", "End")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_replace_multiple_with_one(self):
        """Replace multiple paragraphs with a single one."""
        base = _make_doc("A", "B", "C", "D")
        desired = _make_doc("X")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_replace_one_with_multiple(self):
        """Replace a single paragraph with multiple."""
        base = _make_doc("X")
        desired = _make_doc("A", "B", "C", "D")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_complex_interleaved_changes(self):
        """Mix of adds, deletes, and unchanged paragraphs."""
        base = _make_doc("A", "B", "C", "D", "E")
        desired = _make_doc("A", "X", "C", "Y", "Z")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_unicode_content(self):
        """Test with unicode/emoji content (UTF-16 correctness)."""
        base = _make_doc("Hello")
        desired = _make_doc("Hello", "World \U0001f600")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_long_paragraphs(self):
        """Test with longer paragraph text."""
        base = _make_doc(
            "This is a long paragraph with many words in it.",
            "Another paragraph here.",
        )
        desired = _make_doc(
            "This is a long paragraph with many words in it.",
            "A brand new middle paragraph.",
            "Another paragraph here.",
        )
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_first_keep_rest(self):
        """Delete only the first paragraph."""
        base = _make_doc("A", "B", "C")
        desired = _make_doc("B", "C")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_last_keep_rest(self):
        """Delete only the last paragraph."""
        base = _make_doc("A", "B", "C")
        desired = _make_doc("A", "B")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"
