# Implementation Gap Analysis

## Current State

The current implementation uses an **HTML-based format** with inline styling:

```
Google Docs JSON → html_converter.py → document.html (with embedded styles)
```

**What exists:**
- `html_converter.py` - Converts Google Docs JSON to HTML
- `html_parser.py` - Placeholder for parsing HTML back
- `indexer.py` - UTF-16 index calculation and validation
- `client.py` - DocsClient with pull/diff/push (diff returns empty)

## Target State (per spec)

The spec requires an **XML-based format** with separated, factorized styles:

```
Google Docs JSON → xml_converter.py → document.xml + styles.xml
```

**Key differences:**

| Aspect | Current | Spec |
|--------|---------|------|
| Format | HTML | XML |
| Styles | Inline in document | Separate styles.xml |
| Style IDs | None | 5-char content hashes |
| Lists | Nested `<ul>/<ol>` | Flat `<li>` with attributes |
| Tables | `<tr>/<td>` kept | `<tr>` is sugar, flattened for diff |
| Headings | `<h1>` as output | `<h1>` as sugar for `<p style="HEADING_1">` |
| Multi-element styling | Not supported | `<style class="...">` wrapper |

## Implementation Tasks

### 1. Style Factorization (New)

Create `style_factorizer.py`:
- Collect all text styles from document
- Compute base style (mode for each property)
- Compute deviations per text run
- Group identical deviations → one style per group
- Generate 5-char hash IDs via `style_hash.py` ✅ (exists)
- Output `styles.xml`

### 2. XML Converter (Replace html_converter.py)

Create `xml_converter.py`:
- Convert paragraphs to `<p>`, `<h1>`-`<h6>`, `<title>`, `<subtitle>`, `<li>`
- Apply style classes from factorization
- Wrap multi-element same-style ranges with `<style class="...">`
- Convert inline formatting to `<b>`, `<i>`, `<u>`, `<a>`, etc.
- Handle tables with `<tr>/<td>` (sugar)
- Handle headers/footers/footnotes as separate sections with own base style
- Output `document.xml`

### 3. Desugar Transform (New)

Create `desugar.py`:
- `<h1>` → `<p style="HEADING_1">`
- `<li type="..." level="...">` → `<p bullet="..." level="...">`
- `<tr>/<td>` → flat `<td row="r" col="c">`
- `<b>text</b>` → `<t bold="1">text</t>`
- `<style class="...">` → apply class to children
- Output internal XML for diff

### 4. Diff Engine (Replace html_parser.py)

Create `diff_engine.py`:
- Parse pristine and current internal XML
- Flatten to primitive sequences
- Calculate indexes from structure
- Sequence diff (using difflib or similar)
- Detect: content changes, style changes, structural changes
- Handle `<style>` wrapper additions/removals (content inside inherits)

### 5. batchUpdate Generator (Enhance)

Update request generation:
- Sort operations by descending index
- Content: `insertText`, `deleteContentRange`
- Lists: `createParagraphBullets`, `deleteParagraphBullets`
- Styles: `updateTextStyle`, `updateParagraphStyle`
- Tables: `insertTableRow`, `deleteTableRow`

### 6. Update Client

Update `client.py`:
- `pull()`: Use new XML converter + style factorizer
- `diff()`: Use desugar + diff engine
- `push()`: Use batchUpdate generator

## File Changes Summary

| Action | File |
|--------|------|
| Delete | `html_converter.py` |
| Delete | `html_parser.py` |
| Keep | `indexer.py` (UTF-16 calculation still needed) |
| Keep | `style_hash.py` ✅ |
| Create | `style_factorizer.py` |
| Create | `xml_converter.py` |
| Create | `desugar.py` |
| Create | `diff_engine.py` |
| Update | `client.py` |

## Priority Order

1. **Style factorization** - Foundation for everything else
2. **XML converter** - Generates the new format
3. **Desugar transform** - Needed before diff
4. **Diff engine** - Core functionality
5. **batchUpdate generator** - Complete the loop

## Estimated Scope

- Style factorizer: ~200 lines
- XML converter: ~400 lines (similar complexity to html_converter)
- Desugar: ~150 lines
- Diff engine: ~300 lines
- batchUpdate updates: ~200 lines
- Client updates: ~50 lines

**Total: ~1,300 lines of new/modified code**
