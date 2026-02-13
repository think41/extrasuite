# Implementation Plan: Google Docs Mock API Edge Cases

## Overview
This document outlines the implementation plan for adding missing edge case validations to `mock_api.py` based on the analysis in `EDGE_CASE_ANALYSIS.md`.

## Phase 1: Critical Validations (HIGH Priority)

### 1.1 Surrogate Pair Splitting Protection

**Location**: `_delete_content_range_impl()` in `mock_api.py`

**Implementation**:
```python
def _validate_no_surrogate_pair_split(
    self, segment: dict[str, Any], start_index: int, end_index: int
) -> None:
    """Validate that deletion doesn't split a surrogate pair.

    Args:
        segment: The segment containing the content
        start_index: Start of deletion range
        end_index: End of deletion range

    Raises:
        ValidationError: If deletion would split a surrogate pair
    """
    # Walk through all text content in the range
    for element in segment.get("content", []):
        if "paragraph" in element:
            for para_elem in element["paragraph"].get("elements", []):
                if "textRun" in para_elem:
                    text = para_elem["textRun"].get("content", "")
                    elem_start = para_elem.get("startIndex", 0)

                    # Convert to UTF-16 code units and check boundaries
                    utf16_units = []
                    for char in text:
                        utf16_units.extend(char.encode('utf-16-le'))

                    # Check if start_index or end_index falls within a surrogate pair
                    # Surrogate pairs: high surrogate (0xD800-0xDBFF) + low surrogate (0xDC00-0xDFFF)
                    for i in range(0, len(utf16_units), 2):
                        unit_pos = elem_start + i // 2
                        if i + 1 < len(utf16_units):
                            high = (utf16_units[i+1] << 8) | utf16_units[i]
                            if 0xD800 <= high <= 0xDBFF:
                                # This is a high surrogate, next should be low
                                if i + 3 < len(utf16_units):
                                    low = (utf16_units[i+3] << 8) | utf16_units[i+2]
                                    if 0xDC00 <= low <= 0xDFFF:
                                        # We have a surrogate pair at unit_pos
                                        # Check if deletion boundary falls within it
                                        if (start_index == unit_pos + 1 or
                                            end_index == unit_pos + 1):
                                            raise ValidationError(
                                                f"Cannot delete one code unit of a surrogate pair at index {unit_pos}"
                                            )
```

**Tests to Add**:
```python
def test_delete_surrogate_pair_split_fails():
    """Test that deleting part of a surrogate pair fails."""
    doc = create_document_with_emoji()  # "Hello😀World"
    api = MockGoogleDocsAPI(doc)

    # Try to delete just the high surrogate of 😀
    requests = [{"deleteContentRange": {"range": {"startIndex": 6, "endIndex": 7}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "surrogate pair" in str(exc_info.value).lower()

def test_delete_full_surrogate_pair_succeeds():
    """Test that deleting a full surrogate pair succeeds."""
    doc = create_document_with_emoji()  # "Hello😀World"
    api = MockGoogleDocsAPI(doc)

    # Delete both code units of 😀
    requests = [{"deleteContentRange": {"range": {"startIndex": 6, "endIndex": 8}}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
```

### 1.2 TableCell Final Newline Protection

**Location**: `_delete_content_range_impl()` in `mock_api.py`

**Implementation**:
```python
# In _delete_content_range_impl, add check for table cells:

# After existing segment validation, add:
# Check if we're deleting within a table cell
if self._is_range_in_table_cell(tab, segment_id, start_index, end_index):
    cell_content, cell_end = self._get_table_cell_at_index(tab, segment_id, start_index)
    if end_index >= cell_end:
        raise ValidationError(
            f"Cannot delete the final newline of a table cell. "
            f"Deletion range {start_index}-{end_index} includes final newline at {cell_end - 1}"
        )

def _is_range_in_table_cell(
    self, tab: dict[str, Any], segment_id: str | None, start_index: int, end_index: int
) -> bool:
    """Check if a range is within a table cell."""
    if segment_id is not None:
        return False  # Table cells are only in body

    segment, _ = self._get_segment(tab, segment_id)
    for element in segment.get("content", []):
        if "table" in element:
            table = element["table"]
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_content = cell.get("content", [])
                    if cell_content:
                        cell_start = cell_content[0].get("startIndex", 0)
                        cell_end = cell_content[-1].get("endIndex", 0)
                        if start_index >= cell_start and end_index <= cell_end:
                            return True
    return False

def _get_table_cell_at_index(
    self, tab: dict[str, Any], segment_id: str | None, index: int
) -> tuple[list[dict[str, Any]], int]:
    """Get table cell content and end index containing the given index."""
    segment, _ = self._get_segment(tab, segment_id)
    for element in segment.get("content", []):
        if "table" in element:
            table = element["table"]
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_content = cell.get("content", [])
                    if cell_content:
                        cell_start = cell_content[0].get("startIndex", 0)
                        cell_end = cell_content[-1].get("endIndex", 0)
                        if cell_start <= index < cell_end:
                            return cell_content, cell_end
    raise ValidationError(f"No table cell found at index {index}")
```

**Tests to Add**:
```python
def test_delete_table_cell_final_newline_fails():
    """Test that deleting final newline from table cell fails."""
    doc = create_document_with_table()
    api = MockGoogleDocsAPI(doc)

    # Try to delete the final newline of a cell
    requests = [{"deleteContentRange": {"range": {"startIndex": CELL_END-1, "endIndex": CELL_END}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "final newline of a table cell" in str(exc_info.value).lower()
```

## Phase 2: Important Validations (MEDIUM Priority)

### 2.1 Structural Element Tracking

**Location**: New class or module in `mock_api.py`

**Implementation**:
```python
class DocumentStructureTracker:
    """Track structural elements in a document for validation."""

    def __init__(self, document: dict[str, Any]):
        self.tables: list[tuple[int, int]] = []  # (start, end)
        self.table_of_contents: list[tuple[int, int]] = []
        self.equations: list[tuple[int, int]] = []
        self.section_breaks: list[int] = []  # Just the index

        self._scan_document(document)

    def _scan_document(self, document: dict[str, Any]) -> None:
        """Scan document and record all structural elements."""
        for tab in document.get("tabs", []):
            document_tab = tab.get("documentTab", {})
            body = document_tab.get("body", {})
            self._scan_content(body.get("content", []))

    def _scan_content(self, content: list[dict[str, Any]]) -> None:
        """Recursively scan content for structural elements."""
        for element in content:
            start = element.get("startIndex", 0)
            end = element.get("endIndex", 0)

            if "table" in element:
                self.tables.append((start, end))
            elif "tableOfContents" in element:
                self.table_of_contents.append((start, end))
            elif "equation" in element:
                self.equations.append((start, end))
            elif "sectionBreak" in element:
                self.section_breaks.append(start)

    def validate_delete_range(self, start_index: int, end_index: int) -> None:
        """Validate that deletion doesn't violate structural rules."""
        # Check tables
        for table_start, table_end in self.tables:
            if self._is_partial_overlap(start_index, end_index, table_start, table_end):
                raise ValidationError(
                    f"Cannot partially delete table at {table_start}-{table_end}"
                )
            # Check newline before table
            if start_index < table_start <= end_index:
                raise ValidationError(
                    f"Cannot delete newline before table at index {table_start}"
                )

        # Check TableOfContents
        for toc_start, toc_end in self.table_of_contents:
            if self._is_partial_overlap(start_index, end_index, toc_start, toc_end):
                raise ValidationError(
                    f"Cannot partially delete table of contents at {toc_start}-{toc_end}"
                )
            if start_index < toc_start <= end_index:
                raise ValidationError(
                    f"Cannot delete newline before table of contents at index {toc_start}"
                )

        # Check Equations
        for eq_start, eq_end in self.equations:
            if self._is_partial_overlap(start_index, end_index, eq_start, eq_end):
                raise ValidationError(
                    f"Cannot partially delete equation at {eq_start}-{eq_end}"
                )

        # Check SectionBreaks
        for sb_index in self.section_breaks:
            if start_index < sb_index <= end_index:
                raise ValidationError(
                    f"Cannot delete newline before section break at index {sb_index}"
                )

    def _is_partial_overlap(
        self, del_start: int, del_end: int, elem_start: int, elem_end: int
    ) -> bool:
        """Check if deletion partially overlaps element."""
        # Has overlap but not complete
        has_overlap = del_start < elem_end and del_end > elem_start
        is_complete = del_start <= elem_start and del_end >= elem_end
        return has_overlap and not is_complete
```

### 2.2 Integration into MockGoogleDocsAPI

**Implementation**:
```python
class MockGoogleDocsAPI:
    def __init__(self, initial_document: dict[str, Any]) -> None:
        # ... existing code ...

        # Track structural elements
        self._structure_tracker = DocumentStructureTracker(self._document)

    def _delete_content_range_impl(self, ...):
        # ... existing validation ...

        # Add structural validation
        self._structure_tracker.validate_delete_range(start_index, end_index)

        # ... rest of implementation ...

    def _process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        result = # ... existing processing ...

        # Rebuild structure tracker after any modification
        # (In a real implementation, we'd update it incrementally)
        self._structure_tracker = DocumentStructureTracker(self._document)

        return result
```

**Tests to Add**:
```python
def test_delete_partial_table_of_contents_fails():
    """Test that partially deleting TableOfContents fails."""
    doc = create_document_with_toc()
    api = MockGoogleDocsAPI(doc)

    # Try to partially delete TOC
    requests = [{"deleteContentRange": {"range": {"startIndex": TOC_START+1, "endIndex": TOC_END-1}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "table of contents" in str(exc_info.value).lower()

def test_delete_newline_before_section_break_fails():
    """Test that deleting newline before section break fails."""
    doc = create_document_with_section_break()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteContentRange": {"range": {"startIndex": SB_INDEX-1, "endIndex": SB_INDEX}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "section break" in str(exc_info.value).lower()
```

## Phase 3: Additional Tests and Refinements

### 3.1 Comprehensive Test Suite

**Tests to Add**:
1. `test_insert_text_strips_private_use_area()` - Test U+E000-U+F8FF stripping
2. `test_insert_inline_image_in_footnote_fails()` - Test image in footnote restriction
3. `test_insert_text_at_table_start_fails()` - Test text at table boundary
4. `test_surrogate_pair_various_operations()` - Comprehensive surrogate pair testing

### 3.2 Helper Test Functions

```python
def create_document_with_emoji() -> dict:
    """Create document with emoji for surrogate pair testing."""
    return {
        "documentId": "test_emoji_doc",
        "title": "Emoji Test",
        "tabs": [{
            "tabProperties": {"tabId": "tab1", "title": "Tab 1", "index": 0},
            "documentTab": {
                "body": {
                    "content": [{
                        "startIndex": 1,
                        "endIndex": 13,  # "Hello😀World\n" = 5+2+5+1 = 13
                        "paragraph": {
                            "elements": [{
                                "startIndex": 1,
                                "endIndex": 13,
                                "textRun": {
                                    "content": "Hello😀World\n",
                                    "textStyle": {}
                                }
                            }],
                            "paragraphStyle": {}
                        }
                    }]
                },
                # ... headers, footers, etc.
            }
        }]
    }

def create_document_with_table() -> dict:
    """Create document with a table for cell testing."""
    # ... implementation ...

def create_document_with_toc() -> dict:
    """Create document with TableOfContents."""
    # ... implementation ...

def create_document_with_section_break() -> dict:
    """Create document with SectionBreak."""
    # ... implementation ...
```

## Implementation Order

1. ✅ Create analysis document (DONE)
2. ✅ Create implementation plan (DONE)
3. Add helper functions for test documents
4. Implement surrogate pair validation
5. Implement TableCell final newline protection
6. Add DocumentStructureTracker class
7. Integrate structure tracker into delete validation
8. Add all missing tests
9. Run full test suite and fix any issues
10. Update documentation

## Testing Strategy

1. **Unit Tests**: Test each validation function individually
2. **Integration Tests**: Test complete batchUpdate operations
3. **Edge Case Tests**: Focus on boundary conditions (surrogate pairs, zero-length ranges, etc.)
4. **Regression Tests**: Ensure existing tests still pass

## Success Criteria

- All Phase 1 validations implemented and tested
- All Phase 2 validations implemented and tested
- Test coverage > 90% for edge case validation code
- All existing tests continue to pass
- Documentation updated to reflect new validations
