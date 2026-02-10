# Google Docs Skill

Create and edit Google Documents using the declarative pull-edit-diff-push workflow.

!!! success "Status: Stable"
    This skill is fully supported for production use.

## Overview

The Google Docs skill enables your AI agent to:

- Pull documents into editable local files
- Read and modify document content
- Insert and format text
- Work with tables, lists, and images
- Preview changes before applying
- Push edits back to Google Docs

All editing is declarative - the agent edits local files, and ExtraSuite computes the minimal `batchUpdate` API calls to sync changes.

## The Workflow

```bash
# 1. Pull - download the document
python -m extradoc pull https://docs.google.com/document/d/DOCUMENT_ID/edit

# 2. Edit - modify files in the local folder

# 3. Diff - preview changes (dry run)
python -m extradoc diff ./DOCUMENT_ID/

# 4. Push - apply changes
python -m extradoc push ./DOCUMENT_ID/
```

## On-Disk Format

After `pull`, you'll have:

```
<document_id>/
  document.json           # Document metadata and structure
  content/                # Document content in LLM-friendly format
    ...
  .raw/
    document.json         # Raw API response
  .pristine/
    document.zip          # Original state for diff comparison
```

The agent edits files in this folder. When it runs `push`, ExtraSuite diffs the current state against `.pristine/` and generates the minimal API update.

## Current Capabilities

| Feature | Status |
|---------|--------|
| Read document content | :material-check-circle:{ .text-green } Available |
| Create new documents | :material-check-circle:{ .text-green } Available |
| Insert text | :material-check-circle:{ .text-green } Available |
| Basic formatting | :material-check-circle:{ .text-green } Available |
| Tables | :material-check-circle:{ .text-green } Available |
| Images | :material-clock:{ .text-gray } Planned |
| Headers/Footers | :material-clock:{ .text-gray } Planned |
| Styles | :material-clock:{ .text-gray } Planned |

## Best Practices

### 1. Always Pull Fresh

After pushing changes, the local files become stale. Re-pull before making more edits:

```bash
python -m extradoc push ./DOCUMENT_ID/
python -m extradoc pull https://docs.google.com/document/d/DOCUMENT_ID/edit  # Re-pull!
```

### 2. Preview with Diff

Always preview changes before pushing:

```bash
python -m extradoc diff ./DOCUMENT_ID/
```

This shows the `batchUpdate` JSON that would be sent, without making any API calls.

### 3. Minimal Edits

Only change what's necessary. The diff engine works best with targeted edits rather than wholesale rewrites.

## Error Handling

Common errors:

- **"Document not found"** - Verify the URL and that the document is shared with your service account
- **"Permission denied"** - Check sharing permissions (Viewer won't allow writes)
- **"Rate limit"** - Wait and retry

## Limitations

- Complex formatting may not be fully preserved in the local representation
- Some edge cases in table handling
- Limited image support (planned)

## Roadmap

1. **Image handling** - Insert, resize, and position images
2. **Headers/Footers** - Add page headers and footers
3. **Styles** - Apply and create custom styles
4. **Comments** - Add and resolve comments

---

**Related:**

- [Google Sheets Skill](sheets.md) - For spreadsheet operations
- [Google Slides Skill](slides.md) - For presentations
- [Google Forms Skill](forms.md) - For form operations
