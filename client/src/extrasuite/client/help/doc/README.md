Google Docs - edit documents using GitHub-flavored markdown.

  extrasuite docs pull <url> [output_dir]    Download document as markdown
  extrasuite docs push <folder>              Push local changes to Google Docs
  extrasuite docs create <title>             Create a new document
  extrasuite docs share <url> <emails>       Share with contacts

Pull creates a folder with index.md and a tabs/ directory. Open index.md first
— it lists every heading in every tab with its line number, so you can jump
directly to what you want to edit. Edit the files in tabs/ (one .md per tab);
each file has YAML frontmatter (id, title) at the top — don't remove it. To
add a tab, create a new .md file in tabs/ with frontmatter (set id to "").
Standard GFM is supported: headings, bold/italic/strikethrough, inline code,
fenced code blocks, tables, bullet/numbered/checkbox lists, blockquotes, and
callouts ([!NOTE] [!WARNING] [!INFO] [!DANGER] [!TIP]). Cross-doc heading
links use [text](#Heading Name) or [text](#Tab/Heading Name). Existing images
appear as ![alt](uri) and are read-only. Always re-pull after push.
