# On-Disk Format Specification

Formal specification for the folder structure produced by `serde.serialize()` and consumed by `serde.deserialize()`.

**Authoritative implementation:** `src/extradoc/serde/`

---

## Folder Structure

```
<output_dir>/
  index.xml               # Document outline — lists tabs and headings
  .pristine/
    document.zip          # Zip of the entire output_dir at pull time (baseline for diff)
  <tab_folder>/           # One folder per tab (folder name from index.xml)
    document.xml          # EDITABLE: paragraphs, tables, headers, footers, footnotes
    styles.xml            # EDITABLE: CSS-like style class definitions
    docstyle.xml          # READ-ONLY: DocumentStyle (page size, margins, etc.)
    namedstyles.xml       # READ-ONLY: NamedStyles (NORMAL_TEXT, HEADING_1, etc.)
    objects.xml           # READ-ONLY: InlineObjects (embedded images)
    positionedObjects.xml # READ-ONLY: PositionedObjects (floating images)
    namedranges.xml       # READ-ONLY: NamedRanges
```

Optional files (`docstyle.xml`, `namedstyles.xml`, `objects.xml`, `positionedObjects.xml`, `namedranges.xml`) are written only when the tab has data for them. `document.xml` and `styles.xml` are always present.

### Editable vs Read-Only

| File | Editable | Notes |
|------|----------|-------|
| `index.xml` | Conditionally | Regenerated from Document on each pull. Do not edit existing entries. **Add entries only when creating new tabs from scratch** (see [Authoring New Tabs](#authoring-new-tabs)). |
| `<tab>/document.xml` | **Yes** | Primary editing surface. See grammar below. |
| `<tab>/styles.xml` | **Yes** | Add or modify style classes referenced in document.xml. |
| `<tab>/docstyle.xml` | No | Page layout is not diffed by reconcile. |
| `<tab>/namedstyles.xml` | No | Named style overrides are not diffed by reconcile. |
| `<tab>/objects.xml` | No | Inline objects cannot be created or modified via XML. |
| `<tab>/positionedObjects.xml` | No | Positioned objects cannot be created or modified via XML. |
| `<tab>/namedranges.xml` | No | Named ranges are not diffed by reconcile. |
| `.pristine/document.zip` | No | Baseline snapshot. Never modify. |

---

## `index.xml`

Provides the document outline and maps tab IDs to folder names. Used by `deserialize()` to discover tab folders.

```xml
<doc id="<documentId>" title="<title>" revision="<revisionId>">
  <tab id="<tabId>" title="<tabTitle>" folder="<folderName>"
       nestingLevel="<int>"? iconEmoji="<emoji>"? parentTabId="<id>"?>
    <title>Document title text</title>?
    <subtitle>Subtitle text</subtitle>?
    <h1>Heading text</h1>*
    <h2>...</h2>*
    <h3>...</h3>*
    <!-- Child tabs are nested inside their parent <tab> element -->
    <tab ...>...</tab>*
  </tab>+
</doc>
```

**Attributes:**
- `doc/@revision` — omitted if no revision ID is available
- `tab/@nestingLevel` — 0-based nesting depth; omitted for top-level tabs
- `tab/@parentTabId` — omitted for top-level tabs
- `tab/@iconEmoji` — omitted when no icon is set
- `tab/@folder` — the subfolder name used to locate this tab's files

---

## `<tab>/document.xml`

The primary editing surface. Contains the full content of one tab: body paragraphs, tables, headers, footers, and footnotes.

### Top-level structure

```xml
<tab id="<tabId>" title="<tabTitle>" index="<int>"?>
  <lists>?
    <list id="<listId>">
      <level index="<int>" glyphType="<type>"? glyphFormat="<format>"?
             glyphSymbol="<symbol>"? bulletAlignment="<align>"?
             startNumber="<int>"? class="<styleClass>"?>
    </list>+
  </lists>
  <body>
    <BlockNode>*
  </body>
  <header id="<headerId>">
    <BlockNode>*
  </header>*
  <footer id="<footerId>">
    <BlockNode>*
  </footer>*
  <footnote id="<footnoteId>">
    <BlockNode>*
  </footnote>*
</tab>
```

**Notes:**
- `<lists>` is present only when the tab contains bulleted or numbered lists.
- `<header>`, `<footer>`, `<footnote>` are present only when the tab has those segments.
- Trailing empty paragraphs at the end of each segment are suppressed on output and restored on input.
- The trailing `\n` of each paragraph is suppressed on output and restored on input.
- **`<li>` has two forms:** Pulled documents use `parent="<listId>"` referencing an entry in `<lists>`. New tabs (written from scratch) use `type="bullet"` or `type="decimal"` with `level="0"` — no `<lists>` section is needed. Consecutive `<li>` elements with the same `type` are automatically grouped into one sequential list by the reconciler.

### Block nodes

Block nodes appear inside `<body>`, `<td>`, `<header>`, `<footer>`, `<footnote>`, and `<toc>`.

```
BlockNode ::= ParagraphNode | TableNode | <hr/> | <pagebreak/> | <sectionbreak .../> | TocNode
```

**Paragraphs:**

```xml
<p class="<styleClass>"?>      <!-- normal paragraph -->
  <InlineNode>*
</p>

<h1 class="<styleClass>"? headingId="<id>"?>  <!-- heading (h1..h6) -->
<h2 ...>
...
<h6 ...>
<title ...>                    <!-- document title paragraph -->
<subtitle ...>                 <!-- document subtitle paragraph -->

<li parent="<listId>" level="<int>"? class="<styleClass>"?>  <!-- list item (pulled docs) -->
  <InlineNode>*
</li>
<li type="bullet|decimal" level="<int>"? class="<styleClass>"?>  <!-- list item (new tabs) -->
  <InlineNode>*
</li>
```

**Tables:**

```xml
<table class="<styleClass>"?>
  <col class="<styleClass>"?>*     <!-- one per column -->
  <tr class="<styleClass>"?>
    <td class="<styleClass>"? colspan="<int>"? rowspan="<int>"?>
      <BlockNode>*
    </td>+
  </tr>+
</table>
```

`colspan` and `rowspan` are omitted when 1.

**Other block elements:**

```xml
<hr/>                              <!-- horizontal rule -->
<pagebreak/>                       <!-- page break -->
<sectionbreak
  sectionType="CONTINUOUS|NEXT_PAGE|..."?
  defaultHeaderId="<id>"?
  defaultFooterId="<id>"?
  firstPageHeaderId="<id>"?
  firstPageFooterId="<id>"?
  evenPageHeaderId="<id>"?
  evenPageFooterId="<id>"?
  useFirstPageHeaderFooter="true|false"?
  flipPageOrientation="true|false"?
  pageNumberStart="<int>"?
  marginTop="<dim>"?  marginBottom="<dim>"?
  marginLeft="<dim>"?  marginRight="<dim>"?
  marginHeader="<dim>"?  marginFooter="<dim>"?
  columnProperties="<json>"?
  columnSeparatorStyle="<style>"?
  contentDirection="<direction>"?
/>
<toc>                              <!-- table of contents (read-only content) -->
  <BlockNode>*
</toc>
```

Dimension values (`marginTop`, etc.) use the format `<number>pt` (e.g. `72pt`).

### Inline nodes

Inline nodes appear inside paragraph elements (`<p>`, `<h1>`, `<li>`, etc.).

```
InlineNode ::= TNode | LinkNode | <image .../> | <footnoteref .../>
             | <person .../> | <date .../> | <richlink .../>
             | <autotext .../> | <equation/> | <columnbreak/> | <br/>
```

**Text runs:**

```xml
<t class="<styleClass>"?>text content</t>
```

`class` references a style defined in `styles.xml`. Omitted when no style class applies.

**Hyperlinks:**

```xml
<a href="<url>" class="<styleClass>"? linkType="linkBookmark|linkHeading|linkTab"?>
  <t>link text</t>+
</a>
```

`linkType` is omitted for regular URLs. `href` holds the URL for regular links, the bookmark/heading/tab ID for internal links.

**Other inline elements:**

```xml
<image objectId="<id>"/>          <!-- inline image (read-only) -->
<footnoteref id="<footnoteId>"/>  <!-- footnote marker -->
<person email="<email>" name="<name>"? personId="<id>"?/>
<date dateId="<id>"? timestamp="<ts>"? dateFormat="<fmt>"? timeFormat="<fmt>"?
      locale="<loc>"? timeZoneId="<tz>"? displayText="<text>"?/>
<richlink url="<url>" title="<title>"? mimeType="<mime>"?/>
<autotext type="<type>"?/>        <!-- page number, etc. -->
<equation/>                       <!-- equation (read-only) -->
<columnbreak/>                    <!-- column break -->
<br/>                             <!-- soft line break (Shift+Enter) -->
```

---

## `<tab>/styles.xml`

CSS-like class definitions shared across the tab's content. Paragraphs, text runs, and other elements reference these via `class="<name>"`.

The exact schema is defined by `serde/_styles.py`. Style properties include text formatting (font, size, bold, italic, underline, strikethrough, color, background), paragraph formatting (alignment, spacing, indentation), and table/cell formatting.

Agents may add new style classes or modify existing ones. Do not rename a class that is already referenced in `document.xml` without updating all references.

---

## `<tab>/docstyle.xml`, `namedstyles.xml`, `objects.xml`, `positionedObjects.xml`, `namedranges.xml`

These files store their data as JSON wrapped in a single XML element. They are **read-only**: the reconciler does not diff them and changes will be silently ignored on push.

---

## Editing Rules

1. **Edit only `document.xml` and `styles.xml`** in each tab folder. All other files are read-only.
2. **Do not delete `index.xml`** or the `.pristine/` folder — they are required for diff and push.
3. **Structural IDs** (`id` attributes on `<header>`, `<footer>`, `<footnote>`, `<list>`) must remain stable. Do not change existing IDs; you may add new headers/footers (new `<header>`/`<footer>` elements), which will receive server-assigned IDs on push.
4. **Heading IDs** (`headingId` on `<h1>`-`<h6>`) are assigned by Google Docs. Do not change them; they may be referenced by internal links.
5. **TOC content** is read-only. The reconciler ignores changes inside `<toc>` elements.
6. **Inline images** (`<image objectId="..."/>`) are read-only. The reconciler cannot create or reorder images.
7. **List IDs** referenced by `<li parent="...">` must match an entry in `<lists>`. Do not change list IDs; you may add new list definitions. For new tabs, use `type="bullet"` or `type="decimal"` instead of `parent=` — no `<lists>` section is required, and the reconciler groups consecutive same-type `<li>` items into one sequential list automatically.
8. After push, always re-pull before making further edits — the pristine snapshot must match the live document.

---

## Authoring New Tabs

When writing a new tab folder from scratch (not pulled from the API), all three of the following are required:

### 1. Register the tab in `index.xml`

Add a `<tab>` entry with `id="NEW"` and a unique folder name:

```xml
<doc id="<documentId>" title="..." revision="...">
  <!-- existing tabs ... -->
  <tab id="NEW" title="My New Tab" folder="My_Tab" />
</doc>
```

`deserialize()` discovers tab folders by reading `index.xml`, not by scanning the filesystem. A folder without an `index.xml` entry is silently ignored.

### 2. Create a valid `styles.xml`

The deserializer always reads `styles.xml` — it does not check for its existence first. A minimal valid file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<styles>
  <para class="_default" />
  <listlevel class="_default" indentFirst="18.0pt" indentLeft="36.0pt" />
</styles>
```

### 3. Start `<body>` with a `<sectionbreak>`

The reconciler models a freshly created tab as already containing one section break. If your XML omits it, the reconciler sees a deletion and raises `ReconcileError: Section break deletion is not supported`:

```xml
<body>
  <sectionbreak sectionType="CONTINUOUS" contentDirection="LEFT_TO_RIGHT" columnSeparatorStyle="NONE" />
  <!-- your content here -->
</body>
```

### List items in new tabs

Use `type=` instead of `parent=` since there are no existing list IDs:

```xml
<li type="bullet" level="0">First item</li>
<li type="bullet" level="0">Second item</li>
<li type="decimal" level="0">First numbered item</li>
<li type="decimal" level="0">Second numbered item</li>
<li type="decimal" level="0">Top-level item</li>
<li type="decimal" level="1">Sub-item (nested one level)</li>
<li type="decimal" level="0">Back to top level</li>
```

Consecutive `<li>` elements with the same `type` (uninterrupted by other block elements) are grouped into one sequential list by the reconciler. The result shows 1, 2, 3, 4 — not 1, 1, 1, 1.
