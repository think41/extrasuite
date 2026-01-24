# extraslide

A Python library that simplifies editing Google Slides through SML (Slide Markup Language) - an XML-based markup optimized for programmatic and LLM-driven slide editing.

## Core Concept

Instead of working with complex Google Slides API requests, extraslide lets you:

1. Pull a presentation as SML to a file
2. Modify the SML (programmatically, with an LLM, or in an editor)
3. Diff and apply changes - the library handles the API calls

```python
from extraslide import SlidesClient

client = SlidesClient(gateway_url="https://your-gateway.example.com")
url = "https://docs.google.com/presentation/d/your-presentation-id/edit"

# Pull presentation to file
client.pull(url, "presentation.sml")

# Edit the file (manually, programmatically, or with an LLM)...

# Preview changes (dry run)
requests = client.diff("presentation.sml", "presentation_edited.sml")
for req in requests:
    print(req)

# Apply changes to Google Slides
client.apply(url, "presentation.sml", "presentation_edited.sml")
```

## Why SML?

Google Slides API operations are complex. SML provides:

- **Compact representation**: All slide content in readable XML
- **LLM-friendly**: Language models efficiently edit XML markup
- **Diff-based updates**: Only changed elements are updated
- **Complete coverage**: Supports all major Google Slides element types

## API Reference

### SlidesClient

```python
from extraslide import SlidesClient

client = SlidesClient(gateway_url="https://your-gateway.example.com")
```

### File-based API (Primary)

#### `pull(url, path)`

Fetches a Google Slides presentation and saves it as SML to a file.

```python
client.pull("https://docs.google.com/presentation/d/ID/edit", "presentation.sml")
```

#### `diff(original_path, edited_path) -> list`

Dry-run that returns the batchUpdate requests that would be generated without applying them.

```python
requests = client.diff("presentation.sml", "presentation_edited.sml")
for req in requests:
    print(f"{req['type']}: {req}")
```

#### `apply(url, original_path, edited_path) -> dict`

Applies changes to the presentation and returns the API response.

```python
result = client.apply(url, "presentation.sml", "presentation_edited.sml")
```

### String-based API

For programmatic use, string-based variants are available with the `_s` suffix:

#### `pull_s(url) -> str`

Fetches a presentation and returns it as an SML string.

```python
sml = client.pull_s("https://docs.google.com/presentation/d/ID/edit")
```

#### `diff_s(original_sml, edited_sml) -> list`

Diffs two SML strings and returns the batchUpdate requests.

```python
requests = client.diff_s(original_sml, edited_sml)
```

#### `apply_s(url, original_sml, edited_sml) -> dict`

Applies SML string changes to the presentation.

```python
result = client.apply_s(url, original_sml, edited_sml)
```

## SML Structure

SML uses an HTML-inspired syntax with Tailwind-style utility classes:

```xml
<Presentation id="abc123" title="My Presentation" w="720pt" h="405pt">

  <Images>
    <Img id="img1" url="https://example.com/image.png"/>
  </Images>

  <Masters>
    <Master id="m1" name="Simple Light">
      <!-- Master slide elements -->
    </Master>
  </Masters>

  <Layouts>
    <Layout id="l1" master="m1" name="Title Slide">
      <!-- Layout template elements -->
    </Layout>
  </Layouts>

  <Slides>
    <Slide id="s1" layout="l1" master="m1">
      <TextBox id="title1" class="x-100 y-50 w-500 h-80">
        <P class="text-align-center">
          <T class="text-size-36 font-weight-bold text-color-#333333">
            Slide Title
          </T>
        </P>
      </TextBox>

      <Rect id="shape1" class="x-100 y-200 w-300 h-150 fill-#4285f4 stroke-#000000 stroke-w-1"/>

      <Image id="img1" src="img1" class="x-450 y-200 w-200 h-150"/>
    </Slide>

    <Slide id="s2" layout="l1" master="m1">
      <!-- Second slide -->
    </Slide>
  </Slides>

</Presentation>
```

### Supported Elements

| Element | Description |
|---------|-------------|
| `<TextBox>` | Text container with paragraphs |
| `<Rect>`, `<RoundRect>`, `<Ellipse>` | Basic shapes |
| `<Triangle>`, `<Diamond>`, `<Pentagon>`, `<Hexagon>` | Polygons |
| `<Star5>`, `<Heart>`, `<Cloud>` | Special shapes |
| `<Image>` | Images (references `<Img>` in `<Images>`) |
| `<Line>` | Lines and connectors |
| `<Table>` | Tables with rows and cells |
| `<Video>` | Embedded videos |
| `<WordArt>` | Styled text art |
| `<SheetsChart>` | Embedded Google Sheets charts |
| `<Group>` | Grouped elements |

### Tailwind-Style Classes

All styling uses utility classes:

```xml
<!-- Position and size (in points) -->
<Rect class="x-100 y-200 w-300 h-150"/>

<!-- Fill colors (with optional opacity) -->
<Rect class="fill-#4285f4"/>
<Rect class="fill-#4285f4/80"/>  <!-- 80% opacity -->

<!-- Strokes -->
<Rect class="stroke-#d1d5db stroke-w-2"/>

<!-- Text styling -->
<T class="text-size-24 text-color-#333333 font-family-roboto font-weight-bold"/>

<!-- Paragraph alignment -->
<P class="text-align-center"/>

<!-- Content alignment within shapes -->
<TextBox class="content-middle"/>
```

### Text Content Model

Text uses a paragraph (`<P>`) and text run (`<T>`) structure:

```xml
<TextBox id="tb1" class="x-50 y-100 w-400 h-200">
  <P class="text-align-left">
    <T class="text-size-18">Regular text </T>
    <T class="text-size-18 font-weight-bold">bold text </T>
    <T class="text-size-18 font-style-italic">italic text</T>
  </P>
  <P class="text-align-left">
    <T class="text-size-14">Second paragraph</T>
  </P>
</TextBox>
```

## Examples

### Example 1: Text Replacement

```python
from extraslide import SlidesClient

client = SlidesClient(gateway_url="https://gateway.example.com")
url = "https://docs.google.com/presentation/d/ID/edit"

# Pull to file
client.pull(url, "presentation.sml")

# Read, modify, and write back
from pathlib import Path
sml = Path("presentation.sml").read_text()
modified = sml.replace("{{company_name}}", "Acme Corp")
modified = modified.replace("{{date}}", "2024-01-15")
Path("presentation_edited.sml").write_text(modified)

# Apply changes
client.apply(url, "presentation.sml", "presentation_edited.sml")
```

### Example 2: Using an LLM to Edit Slides

```python
from extraslide import SlidesClient

client = SlidesClient(gateway_url="https://gateway.example.com")
url = "https://docs.google.com/presentation/d/ID/edit"

# Pull presentation
client.pull(url, "presentation.sml")

# Read SML for LLM editing
from pathlib import Path
original = Path("presentation.sml").read_text()

# Send SML to an LLM for editing
prompt = f"""Edit this presentation SML to:
1. Change the title to "Q4 Results"
2. Update the subtitle to "Financial Overview"

{original}

Return only the modified SML."""

modified = llm.generate(prompt)
Path("presentation_edited.sml").write_text(modified)

# Preview before applying
requests = client.diff("presentation.sml", "presentation_edited.sml")
print(f"Will apply {len(requests)} changes")

# Apply changes
client.apply(url, "presentation.sml", "presentation_edited.sml")
```

### Example 3: Preview Changes (Dry Run)

```python
from extraslide import SlidesClient

client = SlidesClient(gateway_url="https://gateway.example.com")
url = "https://docs.google.com/presentation/d/ID/edit"

# Pull and edit
client.pull(url, "presentation.sml")

from pathlib import Path
sml = Path("presentation.sml").read_text()
modified = sml.replace("Draft", "Final")
Path("presentation_edited.sml").write_text(modified)

# See what would change without applying
requests = client.diff("presentation.sml", "presentation_edited.sml")
for req in requests:
    print(f"  {req}")

# Apply if satisfied
if input("Apply changes? (y/n): ").lower() == "y":
    client.apply(url, "presentation.sml", "presentation_edited.sml")
```

## Important: Single-Transaction Model

After applying changes, always re-pull the SML before making more edits:

```python
# First edit
client.pull(url, "original.sml")
# ... edit to edited.sml ...
client.apply(url, "original.sml", "edited.sml")

# For next edit, re-pull (SML is now stale)
client.pull(url, "original.sml")  # Required!
# ... edit to edited.sml ...
client.apply(url, "original.sml", "edited.sml")
```

## Installation

```bash
pip install extraslide
```

## Requirements

- Python 3.9+
- A gateway service for Google API authentication

## Documentation

- **[SML Syntax](./docs/markup-syntax-design.md)** - Complete SML specification
- **[Reconciliation](./docs/sml-reconcilliation-spec.md)** - How diffs are computed and applied
- **[Google Slides API](./docs/googleslides/index.md)** - Underlying API reference

## Project Status

Under Development

This library is functional but still evolving. The API may change.

## License

[MIT License](LICENSE)
