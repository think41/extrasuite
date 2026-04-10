Download a Google Doc as a folder of markdown files.

## Usage

  extrasuite doc pull <url> [output_dir]

## Arguments

  url           Document URL or ID
  output_dir    Output directory (optional, defaults to <document_id>/)

## Output

  index.md             Table of contents with line numbers (read-only, start here)
  tabs/<Name>.md       One markdown file per tab (edit these)
  comments.xml         Comments and replies

Each tab file uses standard GitHub-flavored markdown with YAML frontmatter
for tab identity (id, title). Do not remove the frontmatter.

## Adding a New Tab

Create a new .md file in the tabs/ directory. The title is derived from the
filename (underscores become spaces). Push will create the tab in Google Docs.

## Example

  extrasuite doc pull https://docs.google.com/document/d/abc123
  extrasuite doc pull https://docs.google.com/document/d/abc123 ./my-doc
