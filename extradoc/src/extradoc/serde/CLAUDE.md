## Serde Package — Document ↔ XML Conversion

Bidirectional converter between Google Docs API `Document` objects and an agent-friendly XML format. Agents read and write XML without needing to know the verbose JSON structure or internal rules of the Google Docs API.

## Role in the Pull/Push Workflow

```
pull:  API → Document → serde.serialize() → folder (XMLs + pristine.zip)
edit:  agent modifies XML files
diff:  pristine XML → serde.deserialize() → base Document
       edited XML   → serde.deserialize() → desired Document
       reconcile(base, desired) → list[BatchUpdateDocumentRequest]
push:  sequentially execute each BatchUpdateDocumentRequest
```

## Consistency vs Accuracy

The XML→Document conversion does NOT need to perfectly reproduce the original API Document. It needs to be **consistent**: when both the base and desired Documents go through the same `XML→Document` path, any systematic bias cancels out. The reconciler only sees the delta.

For example, if `direction: LEFT_TO_RIGHT` is dropped on synthetic trailing paragraphs, it's dropped in **both** base and desired — so the reconciler sees no difference and generates no request for it.

This matters for:
- **TOC content** — read-only, agents can't edit it, both sides have the same lossy representation
- **Synthetic trailing paragraphs** — auto-stripped on serialize, auto-added on deserialize
- **Default/empty values** like `avoidWidowAndOrphan: False` — absent and false are semantically equivalent

The only fields where accuracy matters are ones **the agent is expected to change** in the XML.

## Key Files

| File | Direction | Purpose |
|------|-----------|---------|
| `_to_xml.py` | Document → XML | Converts API types to XML models |
| `_from_xml.py` | XML → Document | Converts XML models back to API types |
| `_models.py` | — | Dataclass definitions (`TabXml`, `ParagraphXml`, `TabFiles`, etc.) |
| `_styles.py` | Both | Style extraction, resolution, and CSS-like class system |
| `_tab_extras.py` | Both | Per-tab extras: `DocStyleXml`, `NamedStylesXml`, `InlineObjectsXml`, etc. |
| `_index.py` | Document → XML | Builds the `index.xml` heading outline |
| `_utils.py` | — | Shared utilities (color conversion, dimension parsing) |
| `__init__.py` | — | Public API: `serialize`, `deserialize`, `from_document`, `to_document` |

## Per-Tab Folder Structure

```
<tab_folder>/
  document.xml          # Content: paragraphs, tables, headers, footers, footnotes
  styles.xml            # Factorized CSS-like style classes
  docstyle.xml          # DocumentStyle (margins, page size, etc.) — JSON-in-XML
  namedstyles.xml       # NamedStyles (NORMAL_TEXT, HEADING_1, etc.) — JSON-in-XML
  objects.xml           # InlineObjects (images, etc.) — JSON-in-XML
  positionedObjects.xml # PositionedObjects — JSON-in-XML
  namedranges.xml       # NamedRanges — JSON-in-XML
```

Only `document.xml` and `styles.xml` are always present. The extras are written only when the tab has data for them.

## What the Conversion Handles Automatically

### Trailing newlines on paragraphs
Every paragraph in the Google Docs model ends with `\n`. On output (`_to_xml.py`), trailing `\n` is stripped from text runs. On input (`_from_xml.py`), a `\n` text run is appended to every paragraph.

### Trailing empty paragraphs on segments
Every segment (body, header, footer, footnote, table cell) must end with a paragraph in the Google Docs model. When a segment ends with a non-paragraph element (table, TOC, section break) or is empty, the API requires a synthetic empty paragraph. On output, these are stripped so agents don't see them. On input, they are auto-added if needed.

### Table cell defaults
The API returns default values on every cell (`columnSpan: 1`, `rowSpan: 1`, `backgroundColor: {}`). These are not stored in XML but are restored during deserialization to match API expectations.
