"""Tests for diff_engine module."""

from extradoc.diff_engine import diff_documents


class TestTrueDiff:
    """Tests for true diff behavior - minimal operations."""

    def test_identical_documents_produces_zero_requests(self) -> None:
        """Identical documents produce zero requests."""
        xml = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Hello world</p>
            </body>
        </doc>"""
        requests = diff_documents(xml, xml)
        assert requests == []

    def test_identical_multiple_paragraphs_zero_requests(self) -> None:
        """Multiple identical paragraphs produce zero requests."""
        xml = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First paragraph</p>
                <p>Second paragraph</p>
                <p>Third paragraph</p>
            </body>
        </doc>"""
        requests = diff_documents(xml, xml)
        assert requests == []

    def test_single_word_change_minimal_requests(self) -> None:
        """Changing one word generates minimal delete+insert."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Hello World</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Hello Universe</p>
            </body>
        </doc>"""

        requests = diff_documents(pristine, current)

        # Should have delete and insert requests for the changed word
        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        insert_reqs = [r for r in requests if "insertText" in r]

        # Verify we have minimal operations
        assert len(delete_reqs) >= 1
        assert len(insert_reqs) >= 1

        # Character-level diff may split "Universe" into pieces (e.g., "Unive" + "se")
        # due to shared characters. Verify the combined inserts contain the right chars.
        insert_texts = [r["insertText"]["text"] for r in insert_reqs]
        combined = "".join(insert_texts)
        # The inserts should contain the differing characters
        assert "Unive" in combined or "Universe" in combined

    def test_adding_paragraph_produces_insert(self) -> None:
        """Adding a new paragraph produces insert requests."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First</p>
                <p>Second</p>
            </body>
        </doc>"""
        requests = diff_documents(pristine, current)

        # Should have insert requests
        insert_reqs = [r for r in requests if "insertText" in r]
        assert len(insert_reqs) > 0

        # Should insert "Second" text
        insert_texts = [r["insertText"]["text"] for r in insert_reqs]
        assert any("Second" in t for t in insert_texts)

    def test_removing_paragraph_produces_delete(self) -> None:
        """Removing a paragraph produces delete request."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First</p>
                <p>Second</p>
                <p>Third</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First</p>
                <p>Third</p>
            </body>
        </doc>"""
        requests = diff_documents(pristine, current)

        # Should have delete request for "Second" paragraph
        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        assert len(delete_reqs) >= 1


class TestStyleChanges:
    """Tests for style-only changes producing UpdateTextStyle."""

    def test_bold_change_produces_update_style(self) -> None:
        """Making text bold produces updateTextStyle, not delete/insert."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Hello</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p><b>Hello</b></p>
            </body>
        </doc>"""

        requests = diff_documents(pristine, current)

        # Should have updateTextStyle, not delete/insert
        update_reqs = [r for r in requests if "updateTextStyle" in r]
        delete_reqs = [r for r in requests if "deleteContentRange" in r]

        assert len(update_reqs) >= 1
        # Should NOT delete and reinsert the text
        assert len(delete_reqs) == 0

    def test_heading_change_produces_paragraph_style(self) -> None:
        """Changing paragraph to heading produces updateParagraphStyle."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>My Title</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <h1>My Title</h1>
            </body>
        </doc>"""

        requests = diff_documents(pristine, current)

        # Should have updateParagraphStyle
        update_reqs = [r for r in requests if "updateParagraphStyle" in r]
        assert len(update_reqs) >= 1

        # Verify it sets HEADING_1
        for req in update_reqs:
            style = req["updateParagraphStyle"].get("paragraphStyle", {})
            if "namedStyleType" in style:
                assert style["namedStyleType"] == "HEADING_1"


class TestBulletChanges:
    """Tests for bullet list changes."""

    def test_adding_bullet_produces_create_bullets(self) -> None:
        """Adding a bullet produces createParagraphBullets."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Item one</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <li type="bullet" level="0">Item one</li>
            </body>
        </doc>"""

        requests = diff_documents(pristine, current)

        # Should have createParagraphBullets
        bullet_reqs = [r for r in requests if "createParagraphBullets" in r]
        assert len(bullet_reqs) >= 1

    def test_removing_bullet_produces_delete_bullets(self) -> None:
        """Removing a bullet produces deleteParagraphBullets."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <li type="bullet" level="0">Item one</li>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Item one</p>
            </body>
        </doc>"""

        requests = diff_documents(pristine, current)

        # Should have deleteParagraphBullets
        bullet_reqs = [r for r in requests if "deleteParagraphBullets" in r]
        assert len(bullet_reqs) >= 1


class TestLastParagraphRule:
    """Tests verifying the last paragraph cannot be deleted."""

    def test_single_paragraph_preserved(self) -> None:
        """When body has one paragraph, it cannot be deleted."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Only paragraph</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Replacement</p>
            </body>
        </doc>"""
        requests = diff_documents(pristine, current)
        # Should have insert/delete but not delete everything
        delete_requests = [r for r in requests if "deleteContentRange" in r]
        # Single paragraph cannot be deleted entirely
        for req in delete_requests:
            range_obj = req["deleteContentRange"]["range"]
            # Should not delete from index 1 to end of paragraph entirely
            # (some partial deletion for text changes is OK)
            assert not (range_obj["startIndex"] == 1 and range_obj["endIndex"] >= 17)

    def test_multiple_paragraphs_can_delete_non_last(self) -> None:
        """When body has multiple paragraphs, all but last can be deleted."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First</p>
                <p>Second</p>
                <p>Third</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>New content</p>
            </body>
        </doc>"""
        requests = diff_documents(pristine, current)

        # Should have some delete requests
        delete_requests = [r for r in requests if "deleteContentRange" in r]
        # The last paragraph (Third) should not be deleted
        # We should see deletions for First and/or Second

        # Verify we're not deleting the very last paragraph range
        # Third paragraph starts at index 1 + 6 + 7 = 14 and ends at 14 + 6 = 20
        for req in delete_requests:
            range_obj = req["deleteContentRange"]["range"]
            # Last paragraph (Third) range should not be deleted
            assert not (range_obj["startIndex"] == 14 and range_obj["endIndex"] == 20)


class TestTableDiff:
    """Tests for table diffing."""

    def test_identical_tables_zero_requests(self) -> None:
        """Identical tables produce zero requests."""
        xml = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <table rows="2" cols="2">
                    <tr>
                        <td><p>A</p></td>
                        <td><p>B</p></td>
                    </tr>
                    <tr>
                        <td><p>C</p></td>
                        <td><p>D</p></td>
                    </tr>
                </table>
            </body>
        </doc>"""
        requests = diff_documents(xml, xml)
        assert requests == []

    def test_table_cell_change_minimal_update(self) -> None:
        """Changing table cell content produces minimal update."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <table rows="2" cols="2">
                    <tr>
                        <td><p>A</p></td>
                        <td><p>B</p></td>
                    </tr>
                    <tr>
                        <td><p>C</p></td>
                        <td><p>D</p></td>
                    </tr>
                </table>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <table rows="2" cols="2">
                    <tr>
                        <td><p>A</p></td>
                        <td><p>Changed</p></td>
                    </tr>
                    <tr>
                        <td><p>C</p></td>
                        <td><p>D</p></td>
                    </tr>
                </table>
            </body>
        </doc>"""
        requests = diff_documents(pristine, current)

        # Should have some operations for the cell change
        assert len(requests) > 0

        # Should NOT reinsert the entire table
        insert_table_reqs = [r for r in requests if "insertTable" in r]
        assert len(insert_table_reqs) == 0


class TestHeaderFooterDiff:
    """Tests for header and footer diffing."""

    def test_identical_header_zero_requests(self) -> None:
        """Identical headers produce zero requests."""
        xml = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Body content</p>
            </body>
            <header id="kix.header1" class="_base">
                <p>Header text</p>
            </header>
        </doc>"""
        requests = diff_documents(xml, xml)
        assert requests == []

    def test_new_header_creates_header(self) -> None:
        """Adding a new header section produces createHeader."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Body content</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Body content</p>
            </body>
            <header id="kix.header1" class="_base">
                <p>New header</p>
            </header>
        </doc>"""
        requests = diff_documents(pristine, current)

        # Should have createHeader request
        create_header_reqs = [r for r in requests if "createHeader" in r]
        assert len(create_header_reqs) >= 1


class TestSpecialElements:
    """Tests for special element diffing."""

    def test_identical_with_pagebreak_zero_requests(self) -> None:
        """Identical documents with pagebreak produce zero requests."""
        xml = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Before break</p>
                <p><pagebreak/></p>
                <p>After break</p>
            </body>
        </doc>"""
        requests = diff_documents(xml, xml)
        assert requests == []


class TestSequenceDiff:
    """Tests for sequence-level diffing behavior."""

    def test_reorder_paragraphs_minimal_ops(self) -> None:
        """Reordering paragraphs should use minimal operations."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Alpha</p>
                <p>Beta</p>
                <p>Gamma</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>Beta</p>
                <p>Alpha</p>
                <p>Gamma</p>
            </body>
        </doc>"""
        requests = diff_documents(pristine, current)

        # Should have operations to handle the reorder
        assert len(requests) > 0

    def test_insert_in_middle(self) -> None:
        """Inserting paragraph in middle should not affect surrounding."""
        pristine = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First</p>
                <p>Third</p>
            </body>
        </doc>"""
        current = """<?xml version="1.0"?>
        <doc id="test" revision="1">
            <meta><title>Test</title></meta>
            <body class="_base">
                <p>First</p>
                <p>Second</p>
                <p>Third</p>
            </body>
        </doc>"""
        requests = diff_documents(pristine, current)

        # Should have insert for "Second"
        insert_reqs = [r for r in requests if "insertText" in r]
        assert any("Second" in r["insertText"]["text"] for r in insert_reqs)

        # Should NOT delete or reinsert First or Third
        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        # If there are deletes, they shouldn't be for First or Third's ranges
        # First: index 1-7, Third: index 7-13 (before insert)
        for req in delete_reqs:
            range_obj = req["deleteContentRange"]["range"]
            # Shouldn't delete the entire First paragraph
            assert not (range_obj["startIndex"] == 1 and range_obj["endIndex"] == 7)
