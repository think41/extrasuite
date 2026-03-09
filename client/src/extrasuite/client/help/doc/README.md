Google Docs - edit documents via local XML files.

## Workflow

  extrasuite doc pull <url> [output_dir]   Download document
  # Edit tab folders plus comments.xml
  extrasuite doc push <folder>             Apply changes to Google Docs
  extrasuite doc create <title>            Create a new document

See `extrasuite doc pull --help` for directory layout, agent hints, and critical rules (self-contained).

## Directory Structure

  <document_id>/
    index.xml       Outline, tab mapping, and heading XPaths into document.xml
    comments.xml    Comments and replies
    .pristine/      Internal state - do not edit
    .raw/           Raw API responses - do not edit
    <tab_folder>/
      document.xml  Tab content - this is what you edit
      styles.xml    Named style definitions
      ...           Optional read-only tab metadata files

## document.xml Format

Semantic HTML-like XML for a single tab. The document as a whole is represented
by `index.xml` plus one tab folder per tab. Each tab `document.xml` has a
`<body>` and optional `<header>`, `<footer>`, and `<footnote>` segments. Block
elements inside body/header/footer: `<p>`, `<h1>`-`<h6>`, `<title>`,
`<subtitle>`, `<li>`, `<table>`, `<tr>`, `<td>`. Inline elements can be
written directly inside block elements:

```xml
<tab id="t.0" title="Tab 1" index="0">
  <body>
    <sectionbreak sectionType="CONTINUOUS" contentDirection="LEFT_TO_RIGHT" columnSeparatorStyle="NONE" />
    <h1>Heading</h1>
    <p>A paragraph. Use <t class="emphasis">styled text</t> with classes from styles.xml.</p>
    <p>A <a href="https://example.com">hyperlink</a> in a sentence.</p>
    <li type="bullet">First bullet</li>
    <li type="decimal">Numbered item</li>
  </body>
  <header id="h.abc">
    <p>Document Title</p>
  </header>
  <footer id="f.abc">
    <p>(c) 2026 My Company</p>
  </footer>
</tab>
```

**Inline elements** — write these directly inside `<p>`, `<h1>`-`<h6>`, `<li>`, etc.:

  <t class="s1">text</t>  Apply a named style class from styles.xml
  <a href="URL">text</a>  Hyperlink — text is required

**`<t>` wrapper:** pulled documents use `<t>` to wrap text runs. Use `<t class="name">` to
apply a style class. Bare text directly inside block elements is also valid:

  <p><t class="code">formatted text</t> and plain text</p>

## Tabs, Headers & Footers

**Adding a new tab:** Add a `<tab>` entry to `index.xml` with a unique id and
title, then create a matching tab folder. The id can be any short string not
already used (e.g. `t.summary`, `t.newtab`).

**Adding a header/footer to an existing tab:** Add <header> and/or <footer>
elements inside the <tab>, after </body>. Provide any placeholder id — Google
assigns the real id on push and the re-pulled file will have the real id.

**Headers and footers support the same block elements as <body>.**

**New tab requirements:**
1. Create a `<TabName>/document.xml` file with a `<sectionbreak/>` as the first body element.
2. Optionally create a `<TabName>/styles.xml` file (if omitted it is treated as empty `<styles />`).
3. Add a `<tab>` entry to `index.xml`.

```xml
<!-- New tab with header and footer -->
<tab id="t.summary" title="Summary">
  <body>
    <sectionbreak sectionType="CONTINUOUS" contentDirection="LEFT_TO_RIGHT" columnSeparatorStyle="NONE" />
    <h1>Summary</h1>
    <p>Content here.</p>
  </body>
  <header id="h.new">
    <p>My Document Title</p>
  </header>
  <footer id="f.new">
    <p>(c) 2026 My Company</p>
  </footer>
</tab>
```

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

  extrasuite doc pull --help          Pull flags, folder layout, and critical rules
  extrasuite doc push --help          Push flags
  extrasuite doc diff --help          Offline debugging tool (no auth needed)
  extrasuite doc create --help        Create a new document
  extrasuite doc share --help         Share with trusted contacts

## Reference Docs (detailed)

  extrasuite doc help                       List available reference topics
  extrasuite doc help style-reference       Style properties, inheritance, cell styling
  extrasuite doc help date-time             Date/time element attributes and formats
  extrasuite doc help troubleshooting       Common errors, API limits, XML escaping
