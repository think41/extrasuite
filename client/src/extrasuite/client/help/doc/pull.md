Download a Google Doc as a folder of markdown files.

## Usage

  extrasuite docs pull <url> [output_dir]

## Arguments

  url           Document URL or ID
  output_dir    Output directory (optional, defaults to <document_id>/ in CWD)

## Output

  index.md             Table of contents with line numbers (read-only, start here)
  tabs/<Name>.md       One markdown file per tab (edit these)
  comments.xml         Comments and replies (editable — see below)
  .extrasuite/         Internal snapshot used by push — do not edit

## Working with the files

**index.md** lists every heading in every tab with its line number. Use it to
orient yourself and jump to the exact line you want to edit.

**tabs/*.md** are the editable files. Each begins with YAML frontmatter (id,
title) — do not remove it.

**New tabs**: create a new .md file in tabs/ with frontmatter. The filename
becomes the tab title (underscores become spaces). Push creates the tab.

  ---
  id: ""
  title: My New Tab
  ---

## Markdown features

Standard GFM is supported: headings, bold, italic, strikethrough, `inline code`,
fenced code blocks, bullet/numbered/checkbox lists, pipe tables, and links.
Links to headings in the same doc use `[text](#Heading Name)` or
`[text](#Tab_Name/Heading Name)` for cross-tab.

Blockquotes and callouts are supported:
  > regular blockquote
  > [!NOTE], [!WARNING], [!INFO], [!DANGER], [!TIP]

Images are shown as `![alt](uri)`. The URI is a Google-hosted URL — you can
change the alt text but cannot insert new images via push.

Horizontal rules, footnotes, section breaks, and TOC blocks are pulled as-is
and are read-only.

## Comments

comments.xml is pre-populated with existing comments. To add a reply or
resolve a comment, edit the file directly. Run `extrasuite docs help comments-reference`
for the format.

## Example

  extrasuite docs pull https://docs.google.com/document/d/abc123
  extrasuite docs pull https://docs.google.com/document/d/abc123 ./my-doc
