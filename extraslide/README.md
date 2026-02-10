# extraslide

Declarative Google Slides editing for AI agents. Pull, edit, push.

Part of the [ExtraSuite](https://github.com/think41/extrasuite) project - declarative Google Workspace editing for AI agents.

## Overview

extraslide converts Google Slides to/from SML (Slide Markup Language) - a compact XML format that agents can edit declaratively. The library computes the minimal `batchUpdate` API calls to sync changes back. AI agents (Claude Code, Codex, etc.) read and edit presentations through a simple workflow:

1. **Pull** - Download a presentation as editable SML files
2. **Edit** - Agent modifies the SML based on user instructions
3. **Diff** - Preview changes before applying (dry run)
4. **Push** - Apply changes to Google Slides

The library handles all the complexity of the Google Slides API - agents just edit XML.

## Installation

```bash
pip install extraslide
# or
uvx extraslide --help
```

## Authentication

extraslide uses [extrasuite](https://github.com/think41/extrasuite) for authentication. Each user gets a dedicated service account:

```bash
# One-time login (opens browser)
uvx extrasuite login

# Share your Google Slides file with the service account email shown after login
```

## The Pull-Edit-Diff-Push Workflow

### Step 1: Pull

Download a presentation to a local folder:

```bash
uvx extraslide pull "https://docs.google.com/presentation/d/1abc.../edit"
```

This creates a folder structure:

```
1abc.../
  presentation.json       # Metadata (title, ID, dimensions)
  id_mapping.json         # clean_id -> google_object_id mapping
  styles.json             # Styles for each element (position, fill, stroke, text)
  slides/
    01/content.sml        # Slide 1 content
    02/content.sml        # Slide 2 content
    ...
  .pristine/
    presentation.zip      # Original state for diff comparison
  .raw/
    presentation.json     # Raw API response (for debugging)
```

### Step 2: Edit

The agent edits `slides/NN/content.sml` files based on user instructions. SML uses a minimal XML syntax:

```xml
<Slide>
  <TextBox id="e1" x="100" y="50" w="500" h="80">
    <P><T>Quarterly Report</T></P>
  </TextBox>
  <Rect id="e2" x="50" y="200" w="300" h="150"/>
</Slide>
```

Common edits:
- Change text content inside `<T>` tags
- Modify positions (`x`, `y`) or sizes (`w`, `h`)
- Add/delete elements
- Copy elements (duplicate with same ID, new position, omit w/h)

See [copy-workflow.md](./docs/copy-workflow.md) for the copy-based editing guide.

### Step 3: Diff (Preview)

See what changes will be applied without modifying the original:

```bash
uvx extraslide diff 1abc.../
```

This compares the current `slides/` content against the `.pristine/` copy and outputs the Google Slides API requests that would be generated. No API calls are made.

### Step 4: Push

Apply the changes to Google Slides:

```bash
uvx extraslide push 1abc.../
```

The library sends a `batchUpdate` request to the Google Slides API. All edits appear in Google Drive version history with proper attribution.

## SML Format

Each slide is stored as a separate `content.sml` file with minimal XML:

```xml
<Slide>
  <TextBox id="e1" x="100" y="50" w="500" h="80">
    <P><T>Title text</T></P>
  </TextBox>
  <Rect id="e2" x="50" y="200" w="300" h="150"/>
  <Group id="g1" x="400" y="100">
    <Ellipse id="e3" x="0" y="0" w="50" h="50"/>
    <Ellipse id="e4" x="60" y="0" w="50" h="50"/>
  </Group>
</Slide>
```

### Elements

| Element | Description |
|---------|-------------|
| `<TextBox>` | Text container with paragraphs |
| `<Rect>`, `<Ellipse>`, `<RoundRect>` | Basic shapes |
| `<Line>` | Lines and connectors |
| `<Image>` | Images |
| `<Table>` | Tables with `<Row>` and `<Cell>` |
| `<Group>` | Grouped elements (children use relative positions) |
| `<Video>` | Embedded videos |
| `<SheetsChart>` | Linked Google Sheets charts |

### Text Content

Text uses a paragraph (`<P>`) and text run (`<T>`) structure:

```xml
<TextBox id="e1" x="50" y="100" w="400" h="200">
  <P><T>Regular text </T><T>more text</T></P>
  <P><T>Second paragraph</T></P>
</TextBox>
```

### Positions and Sizes

All positions (`x`, `y`) and sizes (`w`, `h`) are in points:

```xml
<Rect id="e1" x="100" y="200" w="300" h="150"/>
```

For elements inside groups, positions are relative to the group's origin.

### Copying Elements

To copy an element, duplicate its XML with:
- Same `id` as the source element
- New `x`, `y` position
- **Omit `w` and `h`** (this signals a copy)

```xml
<!-- Original -->
<Rect id="e1" x="100" y="100" w="200" h="100"/>

<!-- Copy (omit w/h to signal copy) -->
<Rect id="e1" x="400" y="100"/>
```

See [copy-workflow.md](./docs/copy-workflow.md) for details.

## CLI Reference

```bash
# Pull a presentation
uvx extraslide pull <url_or_id> [output_dir]
uvx extraslide pull "https://docs.google.com/presentation/d/1abc.../edit"
uvx extraslide pull "https://docs.google.com/presentation/d/1abc.../edit" ./my-folder

# Preview changes (dry run)
uvx extraslide diff <folder>
uvx extraslide diff ./1abc.../

# Apply changes
uvx extraslide push <folder>
uvx extraslide push ./1abc.../
```

Also works as a Python module:
```bash
python -m extraslide pull ...
python -m extraslide diff ...
python -m extraslide push ...
```

## Important Notes

### Re-pull After Push

After pushing changes, the local SML becomes stale. Always re-pull before making more edits:

```bash
uvx extraslide push ./1abc.../
uvx extraslide pull "https://docs.google.com/presentation/d/1abc.../edit"  # Re-pull!
# Now safe to edit again
```

### What Can Be Edited

- Text content and styling
- Shape properties (fill, stroke, position, size)
- Add/delete slides
- Add/delete elements
- Copy existing elements
- Tables (content and basic styling)
- Images (can reference existing, limited creation support)
- Charts (read-only, linked to source spreadsheet)

### Styles

Element styles (fill, stroke, text formatting) are stored in `styles.json` and automatically applied when copying elements. You don't need to specify styles in the SML - just copy an element and modify the text/position.

## Documentation

- [Copy-Based Editing Guide](./docs/copy-workflow.md) - How to copy and modify elements
- [SML Syntax Specification](./docs/markup-syntax-design.md) - Full format reference

## Requirements

- Python 3.10+
- Google Slides file shared with your service account

## Part of ExtraSuite

This package is part of the [ExtraSuite](https://github.com/think41/extrasuite) project - a platform for declarative Google Workspace editing by AI agents. ExtraSuite supports Sheets, Docs, Slides, and Forms with a consistent pull-edit-diff-push workflow, with Apps Script support upcoming.

## License

[MIT License](LICENSE)
