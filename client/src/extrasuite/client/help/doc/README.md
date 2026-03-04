Google Docs - edit documents via local XML files.

## Workflow

  extrasuite doc pull <url> [output_dir]   Download document
  # Edit document.xml (and optionally styles.xml, comments.xml)
  extrasuite doc push <folder>             Apply changes to Google Docs
  extrasuite doc create <title>            Create a new document

After push, always re-pull before making more changes.

## Directory Structure

  <document_id>/
    document.xml    Document content - this is what you edit
    styles.xml      Named style definitions
    comments.xml    Comments and replies (if any)
    .pristine/      Internal state - do not edit
    .raw/           Raw API responses - do not edit

## document.xml Format

Semantic HTML-like XML. A document contains one or more tabs. Each tab has a
<body> and optional <header> and <footer>. Block elements inside body/header/
footer: <p>, <h1>-<h6>, <title>, <subtitle>, <li>, <table>, <tr>, <td>.
Inline elements can be written directly inside block elements:

```xml
<doc id="DOCUMENT_ID" revision="REVISION_ID">
  <tab id="t.0" title="Tab 1" class="_base">
    <body>
      <sectionbreak sectionType="CONTINUOUS" contentDirection="LEFT_TO_RIGHT" columnSeparatorStyle="NONE" />
      <h1>Heading</h1>
      <p>A paragraph. Use <t class="emphasis">styled text</t> with classes from styles.xml.</p>
      <p>A <a href="https://example.com">hyperlink</a> in a sentence.</p>
      <li type="bullet">First bullet</li>
      <li type="decimal">Numbered item</li>
    </body>
    <header id="h.abc" class="_base">
      <p>Document Title</p>
    </header>
    <footer id="f.abc" class="_base">
      <p>(c) 2026 My Company</p>
    </footer>
  </tab>
</doc>
```

**Inline elements** — write these directly inside `<p>`, `<h1>`-`<h6>`, `<li>`, etc.:

  <t class="s1">text</t>  Apply a named style class from styles.xml
  <a href="URL">text</a>  Hyperlink — text is required

**`<t>` wrapper:** pulled documents use `<t>` to wrap text runs. Use `<t class="name">` to
apply a style class. Bare text directly inside block elements is also valid:

  <p><t class="code">formatted text</t> and plain text</p>

## Tabs, Headers & Footers

**Adding a new tab:** Add a <tab> element with a unique id and title before </doc>.
The id can be any short string not already used (e.g. t.summary, t.newtab).

**Adding a header/footer to an existing tab:** Add <header> and/or <footer>
elements inside the <tab>, after </body>. Provide any placeholder id — Google
assigns the real id on push and the re-pulled file will have the real id.

**Headers and footers support the same block elements as <body>.**

**New tab requirements:**
1. Create a `<TabName>/document.xml` file with a `<sectionbreak/>` as the first body element.
2. Create a `<TabName>/styles.xml` file (can be empty: `<styles />`).
3. Add a `<tab>` entry to `index.xml`.

```xml
<!-- New tab with header and footer -->
<tab id="t.summary" title="Summary" class="_base">
  <body>
    <sectionbreak sectionType="CONTINUOUS" contentDirection="LEFT_TO_RIGHT" columnSeparatorStyle="NONE" />
    <h1>Summary</h1>
    <p>Content here.</p>
  </body>
  <header id="h.new" class="_base">
    <p>My Document Title</p>
  </header>
  <footer id="f.new" class="_base">
    <p>(c) 2026 My Company</p>
  </footer>
</tab>
```

## Critical Rules

  No newlines inside content elements (<p>, <h1>-<h6>, <li>, <t>, etc.)
  Every <td> must contain at least one <p>, even if empty
  XML-escape special characters: &amp; &lt; &gt; &quot;
  <hr/>, <image/>, <autotext/>, <sectionbreak/> are read-only - cannot add or remove
  <sectionbreak/> must be the first element in every <body> — never delete it
  After a list, add <p></p> before a heading to break out of the list context

## Supported Block Tags

  <p>                Paragraph (class, align, lineSpacing, spaceAbove, spaceBelow)
  <h1> - <h6>        Headings
  <title>            Document title style
  <subtitle>         Document subtitle style
  <li>               List item (type: bullet/decimal/alpha/roman/checkbox)
                     Note: level= is read-only. New lists always start at level 0.
  <table>            Table container
  <tr>               Table row
  <td>               Table cell (must contain at least one <p>)
  <pagebreak/>       Page break (can add/delete — NOT YET IMPLEMENTED, will fail at diff)

Note: <footnote> insertion is not yet supported. Existing footnotes are shown
read-only; to add new footnotes use the Google Docs UI.

## Comments

  comment-ref tags in document.xml are read-only (show where comments are anchored)
  Add replies or resolve comments in comments.xml
  Adding new top-level comments is not supported by the Google API

## Commands

  extrasuite doc pull --help          Pull flags and folder layout
  extrasuite doc push --help          Push flags
  extrasuite doc diff --help          Offline debugging tool (no auth needed)
  extrasuite doc create --help        Create a new document

## Reference Docs (detailed)

  extrasuite doc help                       List available reference topics
  extrasuite doc help style-reference       Style properties, inheritance, cell styling
  extrasuite doc help date-time             Date/time element attributes and formats
  extrasuite doc help troubleshooting       Common errors, API limits, XML escaping
