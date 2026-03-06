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

Start with `index.xml`, not with a full `document.xml` read. It tells you which
tab folder to inspect and gives XPath metadata for indexed headings so you can
jump straight to the relevant section.

Each tab folder's document.xml is the primary file for edits. It contains that
tab's content as semantic XML (headings, paragraphs, lists, tables, etc.).

styles.xml in a tab folder defines named styles referenced by class attributes
in that tab's document.xml. Edit it when you need to add a new style or modify
an existing one.

comments.xml is for adding replies to comments or resolving them. New top-level
comments cannot be added via the API.

## Example

  extrasuite doc pull https://docs.google.com/document/d/abc123
  extrasuite doc pull https://docs.google.com/document/d/abc123 /tmp/docs
