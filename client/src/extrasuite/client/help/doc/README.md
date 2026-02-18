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

Semantic HTML-like XML. Block elements: <p>, <h1>-<h6>, <title>, <subtitle>,
<li>, <table>, <tr>, <td>. Inline: <b>, <i>, <u>, <s>, <a href>, <span class>.

```xml
<doc id="DOCUMENT_ID" revision="REVISION_ID">
  <tab id="t.0" title="Tab 1" class="_base">
    <body>
      <h1>Heading</h1>
      <p>A paragraph with <b>bold</b> and <i>italic</i> text.</p>
      <li type="bullet" level="0">First bullet</li>
      <li type="bullet" level="1">Nested bullet</li>
    </body>
  </tab>
</doc>
```

## Critical Rules

  No newlines inside content elements (<p>, <h1>-<h6>, <li>, <b>, etc.)
  Every <td> must contain at least one <p>, even if empty
  XML-escape special characters: &amp; &lt; &gt; &quot;
  <hr/>, <image/>, <autotext/> are read-only - cannot add or remove

## Supported Block Tags

  <p>                Paragraph (class, align, lineSpacing, spaceAbove, spaceBelow)
  <h1> - <h6>        Headings
  <title>            Document title style
  <subtitle>         Document subtitle style
  <li>               List item (type: bullet/decimal/alpha/roman/checkbox, level: 0-8)
  <table>            Table container
  <tr>               Table row
  <td>               Table cell (must contain at least one <p>)
  <pagebreak/>       Page break (can add/delete)
  <footnote>         Footnote (inline at the marker position)

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
