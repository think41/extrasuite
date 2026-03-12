Download a Google Doc to a local folder.

## Usage

  extrasuite docs pull <url> [output_dir]

## Arguments

  url           Document URL or ID
  output_dir    Output directory (optional)

## Flags

  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

If output_dir is given, files are created directly in output_dir.
Otherwise, creates <document_id>/ in the current directory.

The folder contains:

  document.xml    Document content in semantic XML - this is what you edit
  styles.xml      Named style definitions (edit to add/modify styles)
  comments.xml    Comments and replies (present only if document has comments)
  .pristine/      Snapshot for diff/push comparison - do not edit
  .raw/           Raw API responses for debugging - do not edit

## What to Edit

document.xml is the primary file. It contains all document content as
semantic XML (headings, paragraphs, lists, tables, etc.).

styles.xml defines named styles referenced by class attributes in document.xml.
Edit it when you need to add a new style or modify an existing one.

comments.xml is for adding replies to comments or resolving them.
New top-level comments cannot be added via the API.

## Example

  extrasuite docs pull https://docs.google.com/document/d/abc123
  extrasuite docs pull https://docs.google.com/document/d/abc123 /tmp/docs
