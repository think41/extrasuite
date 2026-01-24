---
name: extraslide
description: Read, edit, and create Google Slides presentations. Use when user asks to work with Google Slides, presentations, or shares a docs.google.com/presentation URL.
---

# Google Slides Skill

Edit Google Slides presentations using SML (Slide Markup Language) - an HTML-inspired format that represents slides as structured markup.

## Initialization

**Step 1: Run environment checks (ALWAYS run first)**
```bash
python3 ~/.claude/skills/extraslide/checks.py
```
Creates virtual environment and installs dependencies. On failure, provides setup instructions.

**Step 2: Verify presentation access**
```bash
~/.claude/skills/extraslide/venv/bin/python ~/.claude/skills/extraslide/verify_access.py <presentation_url>
```
Authenticates via ExtraSuite (opens browser if needed) and confirms access to the presentation. On failure, provides sharing instructions with the service account email.

**Step 3: Execute your code**
```bash
~/.claude/skills/extraslide/venv/bin/python your_script.py
```
All scripts use the skill's venv Python to access installed packages.

---

## Workflow Overview

### The SML Workflow (Pull → Edit → Apply)

Google Slides are edited through a three-step workflow:

```python
import os
import sys
sys.path.insert(0, os.path.expanduser("~/.claude/skills/extraslide"))
from gslide_utils import open_presentation

url = "https://docs.google.com/presentation/d/PRES_ID/edit"
client, pres_id = open_presentation(url)

# 1. PULL: Download presentation as SML
client.pull(url, "presentation.sml")

# 2. EDIT: Modify the SML file (see editing instructions below)
# ... edit presentation.sml and save as presentation_edited.sml ...

# 3. APPLY: Push changes back to Google Slides
result = client.apply(url, "presentation.sml", "presentation_edited.sml")
print(f"Applied {len(result.get('replies', []))} changes")
```

### Preview Changes (Dry Run)

Before applying, preview what changes will be made:

```python
requests = client.diff("presentation.sml", "presentation_edited.sml")
for req in requests:
    print(req)
```

---

## SML Format Basics

SML represents slides as HTML-like markup with Tailwind-inspired classes.

### Document Structure

```xml
<Presentation id="abc123" w="720pt" h="405pt" locale="en">
  <Slides>
    <Slide id="slide_1" layout="layout_1">
      <TextBox id="title" class="x-72 y-144 w-576 h-80 font-family-roboto text-size-36">
        <P><T>Slide Title</T></P>
      </TextBox>
      <Rect id="box1" class="x-100 y-300 w-200 h-100 fill-#4285f4"/>
    </Slide>
  </Slides>
</Presentation>
```

### Text Content Rules (CRITICAL)

**All text MUST be wrapped in `<P>` and `<T>` elements:**

```xml
<!-- CORRECT -->
<TextBox>
  <P><T>Hello World</T></P>
</TextBox>

<!-- WRONG - bare text -->
<TextBox>Hello World</TextBox>

<!-- WRONG - no <T> element -->
<TextBox>
  <P>Hello World</P>
</TextBox>
```

**Multiple paragraphs = multiple `<P>` elements:**

```xml
<TextBox>
  <P><T>First paragraph.</T></P>
  <P><T>Second paragraph.</T></P>
</TextBox>
```

**NEVER use `\n` in text content - create new `<P>` elements instead.**

### Styling Text

Default styles go on the `<TextBox>`, overrides go on `<T>`:

```xml
<TextBox class="font-family-roboto text-size-14 text-color-#333333">
  <P>
    <T>Normal text </T>
    <T class="bold">bold</T>
    <T> and </T>
    <T class="italic text-color-#ef4444">red italic</T>
    <T>.</T>
  </P>
</TextBox>
```

---

## Common Editing Tasks

### Change Text Content

```xml
<!-- Before -->
<P><T>Old heading</T></P>

<!-- After -->
<P><T>New heading</T></P>
```

### Add Styling

```xml
<!-- Before -->
<P><T>Important text</T></P>

<!-- After -->
<P><T class="bold text-color-#ef4444">Important text</T></P>
```

### Change Shape Color

```xml
<!-- Before -->
<Rect class="x-100 y-100 w-200 h-100 fill-#ffffff"/>

<!-- After -->
<Rect class="x-100 y-100 w-200 h-100 fill-#4285f4"/>
```

### Move/Resize Element

```xml
<!-- Before -->
<TextBox class="x-72 y-144 w-400 h-50">

<!-- After - moved right and made wider -->
<TextBox class="x-150 y-144 w-500 h-50">
```

### Add Hyperlink

```xml
<!-- Before -->
<P><T>Click here for details.</T></P>

<!-- After -->
<P>
  <T>Click </T>
  <T class="text-color-#2563eb underline" href="https://example.com">here</T>
  <T> for details.</T>
</P>
```

### Create Bullet List

```xml
<TextBox class="font-family-roboto text-size-14">
  <P class="bullet bullet-disc"><T>First point</T></P>
  <P class="bullet bullet-disc"><T>Second point</T></P>
  <P class="bullet bullet-disc indent-level-1"><T>Sub-point</T></P>
</TextBox>
```

---

## Key SML Classes

### Position & Size
- `x-{n}`, `y-{n}` - Position in points
- `w-{n}`, `h-{n}` - Width/height in points
- `rotate-{deg}` - Rotation in degrees

### Fill Colors
- `fill-#rrggbb` - Hex color (e.g., `fill-#4285f4`)
- `fill-#rrggbb/nn` - With opacity (e.g., `fill-#4285f4/80`)
- `fill-theme-accent1` - Theme color
- `fill-none` - No fill

### Stroke/Outline
- `stroke-#rrggbb` - Stroke color
- `stroke-w-{n}` - Stroke weight in points
- `stroke-dash` - Dashed line
- `stroke-none` - No stroke

### Text
- `font-family-{name}` - Font (roboto, arial, etc.)
- `text-size-{n}` - Font size in points
- `text-color-#rrggbb` - Text color
- `text-align-{left|center|right}` - Horizontal alignment
- `content-{top|middle|bottom}` - Vertical alignment

### Text Runs (`<T>`)
- `bold`, `italic`, `underline`, `line-through`
- `font-weight-{100-900}`
- `href="..."` - Hyperlink

### Shadows
- `shadow`, `shadow-sm`, `shadow-md`, `shadow-lg`
- `shadow-none` - Remove shadow

See `sml-reference.md` in this folder for complete reference.

---

## Range Attributes (Read-Only)

The `range` attribute on `<P>` and `<T>` elements contains character indices:

```xml
<P range="0-24">
  <T range="0-6">Hello </T>
  <T range="6-11">world</T>
</P>
```

**NEVER modify `range` attributes.** They are used internally to track text positions for the diff algorithm.

---

## Debugging Formatting Issues

If the user reports that a slide doesn't look right, you can download a thumbnail to see it:

```python
from gslide_utils import get_thumbnail, list_slides

url = "https://docs.google.com/presentation/d/PRES_ID/edit"

# First, list slides to find the ID
slides = list_slides(url)
for s in slides:
    print(f"Slide {s['index']}: {s['id']} - {s.get('title', 'No title')}")

# Download thumbnail for specific slide
result = get_thumbnail(url, "g12345678", "slide_preview.png")
print(f"Saved to: {result['saved_to']}")
```

**WARNING:** Thumbnail downloads are expensive API operations. Only use when:
- The user explicitly reports formatting problems
- You need to verify visual appearance

---

## Complete Example

```python
import os
import sys
sys.path.insert(0, os.path.expanduser("~/.claude/skills/extraslide"))
from gslide_utils import open_presentation

url = "https://docs.google.com/presentation/d/PRES_ID/edit"
client, pres_id = open_presentation(url)

# Pull presentation
client.pull(url, "presentation.sml")

# Read and modify
with open("presentation.sml") as f:
    sml = f.read()

# Example: Change all blue fills to green
edited_sml = sml.replace("fill-#4285f4", "fill-#34a853")

# Save edited version
with open("presentation_edited.sml", "w") as f:
    f.write(edited_sml)

# Preview changes
requests = client.diff("presentation.sml", "presentation_edited.sml")
print(f"Changes to apply: {len(requests)}")

# Apply changes
if requests:
    result = client.apply(url, "presentation.sml", "presentation_edited.sml")
    print("Changes applied successfully!")
```

---

## String-based API

For programmatic use without files:

```python
# Pull as string
sml = client.pull_s(url)

# Edit the string
edited_sml = sml.replace("Old Title", "New Title")

# Diff strings
requests = client.diff_s(sml, edited_sml)

# Apply from strings
result = client.apply_s(url, sml, edited_sml)
```

---

## Error Handling

```python
import urllib.error

try:
    client.apply(url, "original.sml", "edited.sml")
except urllib.error.HTTPError as e:
    if e.code == 403:
        print("Access denied - check sharing permissions")
    elif e.code == 404:
        print("Presentation not found")
    elif e.code == 429:
        print("Rate limit - wait and retry")
    else:
        print(f"API error: {e}")
except ValueError as e:
    print(f"Invalid URL or no changes: {e}")
```

---

## Best Practices

1. **Always pull fresh before editing** - SML becomes stale after apply
2. **Preview with diff() before apply()** - Verify changes are correct
3. **Don't modify `id` or `range` attributes** - They're internal references
4. **Use explicit `<P><T>` structure** - Never bare text
5. **Use hex colors** - Named colors are not supported
6. **Keep edits minimal** - Only change what's necessary
7. **Re-pull after apply** - The edited SML is now invalid
