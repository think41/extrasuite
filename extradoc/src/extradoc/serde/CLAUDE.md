## Serde Package — Document ↔ Folder Conversion

Bidirectional converter between Google Docs API `Document` objects and an
on-disk folder (markdown or XML). This is the canonical way to read and write
a document for LLM-assisted editing.

**On-disk format spec:** `docs/on-disk-format.md` — authoritative reference for
the folder structure, file names, and grammar.

## Public API (`__init__.py`)

| Symbol | Purpose |
|--------|---------|
| `Serde` (Protocol) | Interface with `serialize()` and `deserialize()` |
| `DeserializeResult` | Dataclass holding `base` and `desired` DocumentWithComments |
| `MarkdownSerde` | `serde.markdown.MarkdownSerde` — canonical implementation |

**`serialize(bundle, folder)`** — writes a `DocumentWithComments` to a folder of
human/LLM-readable files, plus a `.pristine/` snapshot and `.raw/document.json`
so that a future `deserialize` can detect what changed.

**`deserialize(folder)`** — reads the folder, figures out what changed since
`serialize`, and returns a `DeserializeResult` with two documents: `base` (the
original, transport-accurate document) and `desired` (base with the user's edits
merged in via 3-way merge).

## The Core Promise

**The serde will not corrupt anything it doesn't understand.**

Markdown (and XML) are inherently lossy — they cannot represent every property
in a Google Doc (colors, fonts, inline objects, HRs, etc.). The serde's job is
to expose the things it *can* represent for editing, and guarantee that
everything else passes through untouched.

### How the promise is kept: 3-way merge

On `serialize`, the serde saves:
1. **Content files** (`.md` or `.xml`) — the editable representation
2. **`.pristine/document.zip`** — a snapshot of those content files at serialize time
3. **`.raw/document.json`** — the full, transport-accurate API response

On `deserialize`:
1. **base** = load `.raw/document.json` (the full API document, no information loss)
2. **ancestor** = unzip `.pristine/document.zip` and parse it (what the serde wrote)
3. **mine** = parse the current folder (what the user edited)
4. **ops** = `diff(ancestor, mine)` — what changed in the lossy representation
5. **desired** = `apply_ops_to_document(base, ops)` — apply only those changes to base (via `diffmerge/apply_ops.py`)

Because `ancestor` and `mine` go through the same lossy conversion, any
systematic bias cancels out. An HR that markdown doesn't understand appears
identically in both `ancestor` and `mine`, so the diff produces zero ops for it,
and it survives in `desired` unchanged from `base`.

### What the merge preserves

For **unchanged elements**: the raw base element is used as-is (bit-for-bit).

For **changed elements** (e.g., user edited text): the merge starts from the raw
base element and applies only the fields markdown can represent — text content,
bold, italic, strikethrough, underline, links, heading level, monospace. All
other properties (foregroundColor, backgroundColor, font, baselineOffset,
smallCaps, paragraph indentation, bullet properties, inline objects) are
preserved from base.

For **new elements** (e.g., user added a paragraph): the parsed markdown content
is used directly.

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | `Serde` Protocol, `DeserializeResult` dataclass |
| `../diffmerge/apply_ops.py` | 3-way merge engine: `apply_ops_to_document(base, ops)` (moved to diffmerge package) |
| `_models.py` | Shared dataclasses (`TabXml`, `ParagraphXml`, `TabFiles`, etc.) |
| `_styles.py` | Style extraction, resolution, and CSS-like class system |
| `_tab_extras.py` | Per-tab extras: `DocStyleXml`, `NamedStylesXml`, `InlineObjectsXml` |
| `_index.py` | Builds `index.xml` / `index.md` heading outline |
| `_utils.py` | Shared utilities (color conversion, dimension parsing, `serialize_text_run`) |
| `markdown/` | `MarkdownSerde`, `_to_markdown.py`, `_from_markdown.py`, `_special_elements.py` |

## What the Conversion Handles Automatically

**Trailing newlines:** Every paragraph ends with `\n` in the API. On serialize,
trailing `\n` is stripped. On deserialize, a `\n` text run is appended to every
paragraph.

**Trailing empty paragraphs:** Every segment must end with a paragraph in the
API. Synthetic empty trailing paragraphs are stripped on serialize and auto-added
on deserialize.

**Table cell defaults:** The API returns `columnSpan: 1`, `rowSpan: 1`,
`backgroundColor: {}` on every cell. These are omitted from output and restored
on deserialize.

**Named style defaults suppression (`NamedStyleDefaults`):** When serializing,
text-style attributes implied by the paragraph's named style (e.g. `HEADING_1`
is bold) are suppressed. Agents only see overrides. `NamedStyleDefaults` in
`_styles.py` builds a per-named-style lookup.

**List-level indent suppression:** Paragraph `indentFirst` / `indentLeft`
attributes that duplicate the list-level's indent are omitted.

## Testing

See `docs/serde-testing-philosophy.md` for the full testing approach.

Tests validate the core promise at the public interface boundary:

| Test file | Strategy |
|-----------|----------|
| `tests/test_serde_markdown_blackbox.py` | Black-box tests using real golden API responses. Serialize → edit → deserialize → assert changed + assert preserved. |
| `tests/test_serde_markdown_roundtrip.py` | Same pattern with hand-crafted documents for targeted scenarios. |
| `tests/test_serde_markdown_bugs.py` | Regression guards for specific bugs (mostly 3-way merge preservation failures). |
| `tests/test_serde_golden.py` | Golden file snapshot tests. |

Every test asserts both **(a)** what changed is correct and **(b)** nothing else
changed (via the `assert_preserved` helper).
