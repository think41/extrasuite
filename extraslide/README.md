# extraslide

A Python library that converts Google Slides to/from SML (Slide Markup Language) - an XML-based format optimized for AI agent editing.

## Overview

extraslide enables AI agents (Claude Code, Codex, etc.) to read and edit Google Slides through a simple workflow:

1. **Pull** - Download a presentation as an editable SML file
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
  presentation.sml        # The editable SML file
  presentation.json       # Metadata (title, ID)
  .pristine/
    presentation.zip      # Original state for diff comparison
  .raw/
    presentation.json     # Raw API response (for debugging)
```

### Step 2: Edit

The agent edits `presentation.sml` based on user instructions. SML uses an HTML-like syntax that's easy for LLMs to understand and modify:

```xml
<Presentation id="1abc..." title="Q3 Report" w="720pt" h="405pt">
  <Slides>
    <Slide id="s1" layout="TITLE">
      <TextBox id="title" class="x-100 y-50 w-500 h-80">
        <P class="text-align-center">
          <T class="text-size-36 font-weight-bold">Quarterly Report</T>
        </P>
      </TextBox>
    </Slide>
  </Slides>
</Presentation>
```

Common edits:
- Change text content inside `<T>` tags
- Modify styles via CSS-like classes (`text-size-24`, `fill-#4285f4`)
- Add/remove slides or elements
- Reposition elements (`x-100 y-200 w-300 h-150`)

### Step 3: Diff (Preview)

See what changes will be applied without modifying the original:

```bash
uvx extraslide diff 1abc.../
```

This compares `presentation.sml` against the `.pristine/` copy and outputs the Google Slides API requests that would be generated. No API calls are made.

### Step 4: Push

Apply the changes to Google Slides:

```bash
uvx extraslide push 1abc.../
```

The library sends a `batchUpdate` request to the Google Slides API. All edits appear in Google Drive version history with proper attribution.

## SML Format

SML represents slides as XML with Tailwind-style utility classes for styling.

### Document Structure

```xml
<Presentation id="..." title="..." w="720pt" h="405pt">
  <Images>
    <Img id="img1" url="https://..."/>
  </Images>

  <Masters>...</Masters>
  <Layouts>...</Layouts>

  <Slides>
    <Slide id="s1" layout="TITLE" master="m1">
      <!-- Slide content -->
    </Slide>
  </Slides>
</Presentation>
```

### Elements

| Element | Description |
|---------|-------------|
| `<TextBox>` | Text container with paragraphs |
| `<Rect>`, `<Ellipse>`, `<RoundRect>` | Basic shapes |
| `<Line>` | Lines and connectors |
| `<Image>` | Images (references `<Img>` in `<Images>`) |
| `<Table>` | Tables with `<Row>` and `<Cell>` |
| `<Group>` | Grouped elements |
| `<Video>` | Embedded videos |
| `<SheetsChart>` | Linked Google Sheets charts |

### Text Content

Text uses a paragraph (`<P>`) and text run (`<T>`) structure:

```xml
<TextBox id="tb1" class="x-50 y-100 w-400 h-200">
  <P class="text-align-left">
    <T class="text-size-18">Regular text </T>
    <T class="text-size-18 font-weight-bold">bold text</T>
  </P>
  <P>
    <T class="text-size-14">Second paragraph</T>
  </P>
</TextBox>
```

### Styling Classes

Position and size (in points):
```xml
<Rect class="x-100 y-200 w-300 h-150"/>
```

Fill colors (with optional opacity):
```xml
<Rect class="fill-#4285f4"/>
<Rect class="fill-#4285f4/80"/>  <!-- 80% opacity -->
```

Strokes:
```xml
<Rect class="stroke-#000000 stroke-w-2"/>
```

Text styling:
```xml
<T class="text-size-24 text-color-#333333 font-weight-bold font-style-italic"/>
```

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

- ✅ Text content and styling
- ✅ Shape properties (fill, stroke, position, size)
- ✅ Add/delete slides
- ✅ Add/delete elements
- ✅ Tables (content and basic styling)
- ⚠️ Images (can reference existing, limited creation support)
- ⚠️ Charts (read-only, linked to source spreadsheet)

### Masters and Layouts

SML includes `<Masters>` and `<Layouts>` sections for reference, but editing them is not fully supported. Focus edits on the `<Slides>` section.

## Documentation

- [SML Syntax Specification](./docs/markup-syntax-design.md)
- [Diff/Push Reconciliation](./docs/sml-reconciliation-spec.md)

## Requirements

- Python 3.10+
- Google Slides file shared with your service account

## Project Status

**Alpha** - The library is functional but still evolving. SML format and CLI may change.

## License

[MIT License](LICENSE)
