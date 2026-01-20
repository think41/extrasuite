# Google Slides Skill

Create and edit Google Slides presentations using Python and the Google Slides API.

!!! warning "Status: Alpha"
    This skill is in alpha and under active development. APIs may change.

## Overview

The Google Slides skill enables your AI agent to:

- Create new presentations
- Read slide content
- Add and modify slides
- Insert text, shapes, and images
- Apply themes and formatting

## Current Capabilities

| Feature | Status |
|---------|--------|
| Read presentation content | :material-check-circle:{ .text-green } Available |
| Create presentations | :material-check-circle:{ .text-green } Available |
| Add slides | :material-check-circle:{ .text-green } Available |
| Insert text | :material-check-circle:{ .text-green } Available |
| Basic shapes | :material-flask:{ .text-orange } Beta |
| Images | :material-flask:{ .text-orange } Beta |
| Charts | :material-clock:{ .text-gray } Planned |
| Transitions | :material-clock:{ .text-gray } Planned |
| Speaker notes | :material-clock:{ .text-gray } Planned |

## Quick Start

```python
from gslides_utils import open_presentation, create_presentation

# Open existing presentation
pres = open_presentation("https://docs.google.com/presentation/d/.../edit")

# Get slides
slides = pres.get_slides()
print(f"Presentation has {len(slides)} slides")

# Create new presentation
new_pres = create_presentation("My New Presentation")
new_pres.add_slide("Title Slide", layout="TITLE")
```

## Basic Operations

### Opening a Presentation

```python
from gslides_utils import open_presentation

pres = open_presentation("https://docs.google.com/presentation/d/PRESENTATION_ID/edit")
```

### Reading Content

```python
# Get all slides
slides = pres.get_slides()

# Get slide content
for slide in slides:
    print(f"Slide: {slide.title}")
    for element in slide.elements:
        print(f"  - {element.type}: {element.text}")
```

### Creating Presentations

```python
from gslides_utils import create_presentation

# Create empty presentation
pres = create_presentation("New Presentation")

# Create with theme
pres = create_presentation("New Presentation", theme="STREAMLINE")
```

### Adding Slides

```python
# Add title slide
pres.add_slide(layout="TITLE")

# Add content slide
pres.add_slide(layout="TITLE_AND_BODY")

# Add blank slide
pres.add_slide(layout="BLANK")

# Add slide at specific position
pres.add_slide(layout="TITLE_AND_BODY", index=2)
```

## Slide Layouts

| Layout | Description |
|--------|-------------|
| `BLANK` | Empty slide |
| `TITLE` | Title and subtitle |
| `TITLE_AND_BODY` | Title with content area |
| `TITLE_AND_TWO_COLUMNS` | Title with two content areas |
| `TITLE_ONLY` | Title without content |
| `SECTION_HEADER` | Section divider |
| `BIG_NUMBER` | Large number display |

## Working with Text

### Adding Text

```python
# Add text to slide
slide = pres.get_slide(0)
slide.insert_text(
    text="Hello, World!",
    x=100,
    y=100,
    width=400,
    height=50
)
```

### Formatting Text

```python
# Create formatted text box
slide.insert_text(
    text="Important Message",
    x=100,
    y=200,
    font_size=24,
    font_family="Arial",
    bold=True,
    color="#FF0000"
)
```

### Text in Shapes

```python
# Add shape with text
slide.insert_shape(
    shape_type="RECTANGLE",
    x=100,
    y=300,
    width=200,
    height=100,
    text="Click Here",
    fill_color="#0000FF",
    text_color="#FFFFFF"
)
```

## Working with Shapes

### Basic Shapes

```python
# Rectangle
slide.insert_shape("RECTANGLE", x=100, y=100, width=200, height=100)

# Circle (ellipse)
slide.insert_shape("ELLIPSE", x=350, y=100, width=100, height=100)

# Arrow
slide.insert_shape("RIGHT_ARROW", x=100, y=250, width=150, height=50)
```

### Shape Properties

```python
slide.insert_shape(
    shape_type="RECTANGLE",
    x=100,
    y=100,
    width=200,
    height=100,
    fill_color="#FFFF00",
    border_color="#000000",
    border_weight=2
)
```

## Working with Images

```python
# Insert image from URL
slide.insert_image(
    url="https://example.com/image.png",
    x=100,
    y=100,
    width=400,
    height=300
)

# Insert image from Google Drive
slide.insert_image_from_drive(
    file_id="DRIVE_FILE_ID",
    x=100,
    y=100,
    width=400,
    height=300
)
```

## Templates and Placeholders

### Using Templates

```python
# Copy from template
template = open_presentation(template_url)
new_pres = template.copy("New Presentation from Template")

# Replace placeholders
new_pres.replace_text("{{TITLE}}", "Q4 Report")
new_pres.replace_text("{{DATE}}", "January 2024")
new_pres.replace_text("{{AUTHOR}}", "John Smith")
```

### Working with Placeholders

```python
# Get slide with placeholders
slide = pres.get_slide(0)

# Update title placeholder
slide.update_placeholder("TITLE", "New Title")

# Update body placeholder
slide.update_placeholder("BODY", "Content goes here")
```

## Error Handling

```python
from gslides_utils import open_presentation, PresentationNotFound, PermissionError

try:
    pres = open_presentation(url)
except PresentationNotFound:
    print("Presentation not found or not shared")
except PermissionError:
    print("No permission to access presentation")
```

## Best Practices

### 1. Use Templates

For consistent presentations:

```python
# Start from template
template = open_presentation(company_template_url)
new_pres = template.copy("Weekly Report")

# Fill in content
new_pres.replace_text("{{TITLE}}", "Weekly Status Report")
```

### 2. Batch Updates

Group changes for efficiency:

```python
# WRONG: Multiple API calls
slide.insert_text("Line 1", x=100, y=100)
slide.insert_text("Line 2", x=100, y=150)

# CORRECT: Batch request
pres.batch_update([
    {"insert_text": {...}},
    {"insert_text": {...}}
])
```

### 3. Consistent Styling

Define styles upfront:

```python
# Define constants
TITLE_STYLE = {
    "font_size": 36,
    "font_family": "Arial",
    "bold": True,
    "color": "#333333"
}

BODY_STYLE = {
    "font_size": 18,
    "font_family": "Arial",
    "color": "#666666"
}

# Use consistently
slide.insert_text("Title", **TITLE_STYLE, x=50, y=50)
slide.insert_text("Body text", **BODY_STYLE, x=50, y=150)
```

## Limitations

### Alpha Limitations

- Complex animations not supported
- Limited chart integration
- Some layout options unavailable

### API Limitations

- Maximum slides: 100 per presentation
- Maximum elements per slide: 500
- Maximum image size: 25MB
- Rate limits: 600 requests per minute per user

## Use Cases

### Automated Reports

```python
# Generate weekly report
pres = create_presentation(f"Weekly Report - Week {week_number}")

# Title slide
pres.add_slide(layout="TITLE")
slide = pres.get_slide(0)
slide.update_placeholder("TITLE", f"Week {week_number} Report")
slide.update_placeholder("SUBTITLE", date.today().strftime("%B %d, %Y"))

# Metrics slide
pres.add_slide(layout="TITLE_AND_BODY")
# Add metrics content...
```

### Presentation from Data

```python
# Create presentation from data
data = get_monthly_data()  # From database or sheet

pres = create_presentation("Monthly Review")

for metric in data.metrics:
    pres.add_slide(layout="TITLE_AND_BODY")
    slide = pres.get_slide(-1)
    slide.update_placeholder("TITLE", metric.name)
    slide.update_placeholder("BODY", f"Value: {metric.value}\nChange: {metric.change}%")
```

## Roadmap

### Planned Features

1. **Charts** - Native chart creation from data
2. **Transitions** - Slide transition effects
3. **Animations** - Element animations
4. **Speaker notes** - Add and edit speaker notes
5. **Themes** - Apply and customize themes

### Feedback

We're actively developing this skill. Share feedback or report issues through your internal support channels.

---

**Related:**

- [Google Sheets Skill](sheets.md) - For spreadsheet operations
- [Google Docs Skill](docs.md) - For document operations
- [Skill Customization](../customization/skill-customization.md) - Create custom skills
