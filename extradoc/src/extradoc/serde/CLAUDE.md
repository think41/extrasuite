## Serde Package — Document ↔ XML Conversion

Bidirectional converter between Google Docs API `Document` objects and the on-disk XML folder. This is the canonical way to read and write the XML representation of a document.

**On-disk format spec:** `docs/on-disk-format.md` — authoritative reference for the folder structure, file names, and XML grammar.

## Public API (`__init__.py`)

| Function | Purpose |
|----------|---------|
| `serialize(doc, path)` | Write `Document` → folder of XML files |
| `deserialize(folder)` | Read folder → `Document` (no indices) |
| `from_document(doc)` | Convert `Document` → `(IndexXml, dict[folder, TabFiles])` without I/O |
| `to_document(tabs, ...)` | Convert `dict[folder, TabFiles]` → `Document` without I/O |

Both `deserialize` and `to_document` return a `Document` without indices. Call `reindex_document()` from `reconcile._core` if indices are needed.

## Consistency vs Accuracy

The `XML → Document` path does not need to perfectly reproduce the API's `Document`. It needs to be **consistent**: both the base and desired `Document` objects go through the same path, so any systematic bias cancels out in the reconciler's diff.

Fields where accuracy does NOT matter:
- **TOC content** — read-only, both sides have the same lossy representation
- **Synthetic trailing paragraphs** — auto-stripped on serialize, auto-added on deserialize
- **Default/empty values** — `avoidWidowAndOrphan: False` and absent are equivalent

Fields where accuracy DOES matter: anything the agent is expected to change in the XML.

## Key Files

| File | Direction | Purpose |
|------|-----------|---------|
| `_to_xml.py` | Document → XML | Converts API types to XML models |
| `_from_xml.py` | XML → Document | Converts XML models back to API types |
| `_models.py` | — | Dataclass definitions (`TabXml`, `ParagraphXml`, `TabFiles`, etc.) |
| `_styles.py` | Both | Style extraction, resolution, and CSS-like class system |
| `_tab_extras.py` | Both | Per-tab extras: `DocStyleXml`, `NamedStylesXml`, `InlineObjectsXml`, etc. |
| `_index.py` | Document → XML | Builds `index.xml` heading outline |
| `_utils.py` | — | Shared utilities (color conversion, dimension parsing) |
| `__init__.py` | — | Public API |

## What the Conversion Handles Automatically

**Trailing newlines:** Every paragraph ends with `\n` in the API. On serialize, trailing `\n` is stripped. On deserialize, a `\n` text run is appended to every paragraph.

**Trailing empty paragraphs:** Every segment must end with a paragraph in the API. Synthetic empty trailing paragraphs are stripped on serialize and auto-added on deserialize.

**Table cell defaults:** The API returns `columnSpan: 1`, `rowSpan: 1`, `backgroundColor: {}` on every cell. These are omitted from XML and restored on deserialize.

**Named style defaults suppression (`NamedStyleDefaults`):** When serializing, text-style attributes that are already implied by the paragraph's named style (e.g. `HEADING_1` is bold by default) are suppressed from the XML output. This keeps the XML minimal — agents only see and write the attributes that override the named style. `NamedStyleDefaults` in `_styles.py` builds a per-named-style lookup of default text-style attrs from the document's `namedStyles` section.

**List-level indent suppression:** Paragraph `indentFirst` / `indentLeft` attributes that merely duplicate the list-level's own indent definition are omitted. This prevents agents from seeing redundant indent noise on every list item.
