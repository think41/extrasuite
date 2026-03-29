Download a Google Doc in markdown format.

## Usage

  extrasuite docs pull-md <url> [output_dir]

## Arguments

  url           Document URL or ID
  output_dir    Output directory (optional)

## Flags

  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

If output_dir is given, files are created directly in output_dir.
Otherwise, creates <document_id>/ in the current directory.

The folder contains:

  index.md        Table of contents with line numbers for each heading per tab
  <Tab_Name>.md   One markdown file per tab (e.g. Tab_1.md, Introduction.md)
  index.xml       Internal metadata used by push-md — do not edit
  comments.xml    Comments and replies (present only if document has comments)
  .pristine/      Snapshot for diff/push comparison — do not edit
  .raw/           Raw API responses for debugging — do not edit

## Navigating with index.md

Always read index.md first. It shows:
  - Which file each tab is in
  - The line number of every heading in each file

To read only a specific section, use the line numbers from index.md.
For example, if "## Installation" is at line 42 in Tab_1.md, you can
read just that section instead of the entire file.

## What to Edit

Edit the <Tab_Name>.md files directly. Each file contains the full content
of one tab in standard markdown:

  Headings:    # H1, ## H2, ### H3
  Inline:      **bold**, *italic*, ~~strikethrough~~, <u>underline</u>
  Links:       [text](url)
  Lists:       - bullet, 1. numbered, - [ ] checkbox
  Tables:      | col | col |
  Code blocks: ```lang ... ```
  Callouts:    > [!WARNING], > [!INFO], > [!NOTE], > [!DANGER], > [!TIP]
  Blockquotes: > text
  Footnotes:   [^note] plus a matching [^note]: definition

Limits to remember:
  Horizontal rules pulled from Docs are read-only
  TOC / opaque pulled-only blocks are read-only
  New-tab header/footer creation in an existing multi-tab doc needs two pushes

Do NOT edit index.md, index.xml, comments.xml, or files in .pristine/ or .raw/.
index.md is regenerated on each pull — your edits will be lost.

## Example

  extrasuite docs pull-md https://docs.google.com/document/d/abc123
  extrasuite docs pull-md https://docs.google.com/document/d/abc123 /tmp/docs
