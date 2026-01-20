# Google Docs Skill

Create and edit Google Documents using Python and the Google Docs API.

!!! warning "Status: Alpha"
    This skill is in alpha and under active development. APIs may change.

## Overview

The Google Docs skill enables your AI agent to:

- Create new documents
- Read document content
- Insert and modify text
- Apply formatting
- Work with tables, lists, and images

## Current Capabilities

| Feature | Status |
|---------|--------|
| Read document content | :material-check-circle:{ .text-green } Available |
| Create new documents | :material-check-circle:{ .text-green } Available |
| Insert text | :material-check-circle:{ .text-green } Available |
| Basic formatting | :material-flask:{ .text-orange } Beta |
| Tables | :material-flask:{ .text-orange } Beta |
| Images | :material-clock:{ .text-gray } Planned |
| Headers/Footers | :material-clock:{ .text-gray } Planned |
| Styles | :material-clock:{ .text-gray } Planned |

## Quick Start

```python
from gdocs_utils import open_document, create_document

# Open existing document
doc = open_document("https://docs.google.com/document/d/.../edit")

# Get content
content = doc.get_content()
print(content.body)

# Create new document
new_doc = create_document("My New Document")
new_doc.insert_text("Hello, World!")
```

## Basic Operations

### Opening a Document

```python
from gdocs_utils import open_document

doc = open_document("https://docs.google.com/document/d/DOCUMENT_ID/edit")
```

### Reading Content

```python
# Get full content
content = doc.get_content()

# Get plain text
text = doc.get_plain_text()

# Get structured content (paragraphs, lists, tables)
structure = doc.get_structure()
```

### Creating Documents

```python
from gdocs_utils import create_document

# Create empty document
doc = create_document("New Document")

# Create in specific folder
doc = create_document("New Document", folder_id="FOLDER_ID")
```

### Inserting Text

```python
# Insert at end
doc.insert_text("New paragraph")

# Insert at specific index
doc.insert_text("Inserted text", index=10)

# Insert with formatting
doc.insert_text("Bold text", bold=True)
doc.insert_text("Heading", style="HEADING_1")
```

## Working with Text

### Replacing Text

```python
# Replace all occurrences
doc.replace_text("old text", "new text")

# Replace with regex
doc.replace_regex(r"\d{4}-\d{2}-\d{2}", "DATE_PLACEHOLDER")
```

### Formatting Text

```python
# Apply formatting to range
doc.format_range(
    start_index=0,
    end_index=100,
    bold=True,
    italic=False,
    font_size=12,
    font_family="Arial"
)

# Apply paragraph style
doc.apply_style(
    start_index=0,
    end_index=50,
    style="HEADING_2"
)
```

## Working with Tables

```python
# Insert table
doc.insert_table(rows=3, columns=4)

# Insert table with data
data = [
    ["Name", "Role", "Department"],
    ["Alice", "Engineer", "R&D"],
    ["Bob", "Manager", "Sales"]
]
doc.insert_table_with_data(data)
```

## Working with Lists

```python
# Create bullet list
items = ["First item", "Second item", "Third item"]
doc.insert_bullet_list(items)

# Create numbered list
doc.insert_numbered_list(items)
```

## Error Handling

```python
from gdocs_utils import open_document, DocumentNotFound, PermissionError

try:
    doc = open_document(url)
except DocumentNotFound:
    print("Document not found or not shared")
except PermissionError:
    print("No permission to access document")
```

## Best Practices

### 1. Batch Updates

Group multiple changes into a single request:

```python
# WRONG: Multiple API calls
doc.insert_text("Line 1")
doc.insert_text("Line 2")
doc.insert_text("Line 3")

# CORRECT: Single batch request
doc.batch_update([
    {"insert_text": {"text": "Line 1\n", "index": 1}},
    {"insert_text": {"text": "Line 2\n", "index": -1}},
    {"insert_text": {"text": "Line 3\n", "index": -1}}
])
```

### 2. Preserve Formatting

When replacing text, preserve existing formatting:

```python
doc.replace_text("placeholder", "actual value", preserve_formatting=True)
```

### 3. Use Templates

For consistent documents, start with a template:

```python
# Copy template
template_doc = open_document(template_url)
new_doc = template_doc.copy("New Document from Template")

# Replace placeholders
new_doc.replace_text("{{NAME}}", "John Smith")
new_doc.replace_text("{{DATE}}", "2024-01-15")
```

## Limitations

### Alpha Limitations

- Complex formatting may not be fully preserved
- Some edge cases in table handling
- Limited image support

### API Limitations

- Maximum document size: 1,048,576 characters
- Maximum image size: 50MB
- Rate limits: 300 requests per minute per user

## Roadmap

### Planned Features

1. **Image handling** - Insert, resize, and position images
2. **Headers/Footers** - Add page headers and footers
3. **Styles** - Apply and create custom styles
4. **Comments** - Add and resolve comments
5. **Suggestions** - Work with suggestion mode

### Feedback

We're actively developing this skill. Share feedback or report issues through your internal support channels.

---

**Related:**

- [Google Sheets Skill](sheets.md) - For spreadsheet operations
- [Google Slides Skill](slides.md) - For presentations
- [Skill Customization](../customization/skill-customization.md) - Create custom skills
