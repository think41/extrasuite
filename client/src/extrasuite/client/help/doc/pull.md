Download a Google Doc to a local folder.

## Usage

  extrasuite doc pull <url> [output_dir]

## Arguments

  url           Document URL or ID
  output_dir    Output directory (default: current directory)

## Flags

  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

Creates <output_dir>/<document_id>/ with:

  index.xml       Document outline, tab mapping, and heading XPaths into document.xml
  comments.xml    Comments and replies
  .pristine/      Snapshot for diff/push comparison - do not edit
  .raw/           Raw API responses for debugging - do not edit
  <tab_folder>/   One folder per document tab
    document.xml  Tab content in semantic XML - this is what you edit
    styles.xml    Named style definitions (edit to add/modify styles)
    ...           Optional read-only tab metadata files

## What to Edit

Each tab folder's document.xml is the primary file for edits. It contains that
tab's content as semantic XML (headings, paragraphs, lists, tables, etc.).

styles.xml in a tab folder defines named styles referenced by class attributes
in that tab's document.xml. Edit it when you need to add a new style or modify
an existing one.

comments.xml is for adding replies to comments or resolving them. New top-level
comments cannot be added via the API.

## Agent Hints

- Start with `index.xml` — it contains the outline, tab mapping, and heading XPaths
- Use `tab/@folder` and heading `@xpath` to navigate directly to the target section
- Read only until the next indexed heading — avoid full-file rewrites

## Critical Rules

  No newlines inside content elements (<p>, <h1>-<h6>, <li>, <t>, etc.)
  Every <td> must contain at least one <p>, even if empty
  XML-escape special characters: &amp; &lt; &gt; &quot;
  <hr/>, <image/>, <autotext/>, <sectionbreak/> are read-only — cannot add or remove
  <sectionbreak/> must be the first element in every <body> — never delete it
  After a list, add <p></p> before a heading to break out of the list context
  Always re-pull before making further changes after a push

## Example

  extrasuite doc pull https://docs.google.com/document/d/abc123
  extrasuite doc pull https://docs.google.com/document/d/abc123 /tmp/docs
