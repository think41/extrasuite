# Plan: End-to-End Tests for extradoc

## Goal

Add a `tests/test_e2e.py` test suite that validates the complete pull→edit→diff→push cycle using `MockGoogleDocsAPI`. Each test starts from a golden document, modifies the XML, and asserts that `reconcile` produces batches that — when applied to the mock — yield a document matching the desired state.

## Pattern (from `extradoc/CLAUDE.md`)

Every test follows this call stack:

1. Load golden JSON → `Document.model_validate(raw)` → `serde.serialize(doc, tmp_dir)` — establish baseline on disk
2. Write `.pristine/document.zip` from the serialized output — mirrors what `DocsClient.pull()` does
3. Edit XML files in `tmp_dir` to represent the desired state
4. `serde.deserialize(pristine_dir)` → `base: Document`; `serde.deserialize(tmp_dir)` → `desired: Document`
5. `reindex_document(base)`, `reindex_document(desired)`
6. `reconcile(base, desired)` → `batches: list[BatchUpdateDocumentRequest]`
7. `verify(base, batches, desired)` → `(ok, diffs)` — asserts via `documents_match`

Step 7 uses `verify()` from `extradoc/src/extradoc/reconcile/_core.py:537`. It internally creates `MockGoogleDocsAPI`, runs all batches with `resolve_deferred_ids` between them, and calls `documents_match` on the result.

## Fixtures

**`golden_doc(id)` factory** — loads `tests/golden/<id>.json`, returns `Document`. Available golden files:
- `1YicNYwId9u4okuK4uNfWdTEuKyS1QWb1RcnZl9eVyTc` — single-tab doc with lists, images
- `14nMj7vggV3XR3WQtYcgrABRABjKk-fqw0UQUCP25rhQ` — 3-tab doc with tables, horizontal rules
- `15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs` — 2-tab doc

**`pulled(doc, tmp_path)` fixture** — calls `serde.serialize(doc, tmp_path)` and writes the pristine zip; returns the folder path. This is the state a freshly-pulled document is in.

**Helper `load_base(folder)`** — unzips `.pristine/document.zip` into a temp dir, calls `serde.deserialize()`, returns `Document`.

**Helper `run_diff_and_verify(folder)`** — deserializes base and desired, calls `reconcile`, calls `verify`, asserts `ok`. Returns `(batches, diffs)` for spot-checks.

## Test Scenarios

| Test | Golden | XML Edit | Assertion focus |
|------|--------|----------|-----------------|
| `test_no_changes` | single-tab | none | `batches` empty / all requests empty |
| `test_add_paragraph_at_end` | single-tab | append `<p>` to `<body>` in document.xml | ok=True |
| `test_delete_paragraph` | single-tab | remove a `<p>` from body | ok=True |
| `test_edit_paragraph_text` | single-tab | change text content of a `<t>` | ok=True |
| `test_change_heading_level` | single-tab | rename `<h1>` to `<h2>` | ok=True |
| `test_add_list_item` | single-tab | append `<li>` to existing list | ok=True |
| `test_add_table_row` | table doc | append `<tr>` with `<td>` cells | ok=True |
| `test_tab_title_rename` | multi-tab | change `title` attr on `<tab>` in document.xml | ok=True |
| `test_edit_in_second_tab` | 3-tab doc | edit body of tab 2 | ok=True |
| `test_add_header` | single-tab | add `<header id="h1">...</header>` element | ok=True; 2+ batches returned |

## XML Editing Approach

Tests edit XML using `xml.etree.ElementTree` (stdlib) or direct string/path manipulation. No lxml dependency. Pattern:

```
tree = ET.parse(folder / "tab_1" / "document.xml")
root = tree.getroot()
# ... mutate root ...
tree.write(folder / "tab_1" / "document.xml", encoding="unicode", xml_declaration=False)
```

The tab folder name comes from `index.xml` — read it first to find `<tab folder="...">`.

## Key Interfaces

| Symbol | File | Used for |
|--------|------|----------|
| `Document.model_validate(raw)` | `extradoc/src/extradoc/api_types/_generated.py` | Load golden JSON |
| `serde.serialize(doc, path)` | `extradoc/src/extradoc/serde/__init__.py` | Write to disk |
| `serde.deserialize(folder)` | `extradoc/src/extradoc/serde/__init__.py` | Load back to Document |
| `IndexXml.from_xml_string(...)` | `extradoc/src/extradoc/serde/_models.py` | Find tab folder names |
| `reindex_document(doc)` | `extradoc/src/extradoc/reconcile/_core.py` | Compute indices before reconcile |
| `reconcile(base, desired)` | `extradoc/src/extradoc/reconcile/_core.py` | Generate batches |
| `verify(base, batches, desired)` | `extradoc/src/extradoc/reconcile/_core.py` | Run mock + compare |
| `documents_match(actual_dict, desired_dict)` | `extradoc/src/extradoc/reconcile/_comparators.py` | Called inside verify; also usable for spot-checks |

## Notes on `verify()`

`verify()` at `extradoc/src/extradoc/reconcile/_core.py:537`:
- Creates `MockGoogleDocsAPI(base)` (will need typed interface from mock-typed-interface plan)
- Runs each batch: converts `Request` objects to dicts for mock, collects responses
- Calls `documents_match(mock.get_dict(), desired_dict)` — both as dicts

If the mock-typed-interface plan has been completed, `verify()` will call `MockGoogleDocsAPI(base)` directly. If not yet completed, tests can still run since `verify()` handles the conversion internally.

## File Location

**New file:** `extradoc/tests/test_e2e.py`

Golden files are at `extradoc/tests/golden/`. Tests should use relative paths anchored to `Path(__file__).parent / "golden"`.

## Dependency on Other Plans

- **Independent of mock-typed-interface plan** — `verify()` already handles the dict conversion internally, so e2e tests work regardless of whether the mock interface has been typed yet.
- **Independent of client-migration plan** — tests call `serde` and `reconcile` directly, not through `DocsClient`. The pristine-zip helpers in tests can be written inline without referencing `client.py`.
