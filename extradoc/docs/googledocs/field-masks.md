# Use Field Masks

Field masks enable API callers to specify which fields a request should return or modify. This approach allows the API to avoid unnecessary work and improves performance. The Google Docs API employs field masks for both read and update operations.

## Reading with Field Masks

Since documents can be substantial, developers often don't require every component of the Document resource. The `fields` URL parameter limits response data.

### Format Specifications

- Multiple fields use comma separation
- Subfields use dot notation
- Field names accept both camelCase and underscore_separated formats
- Multiple subfields from the same type can be grouped in parentheses

### Example Request

```
GET https://docs.googleapis.com/v1/documents/documentId?fields=title,tabs(documentTab(body.content(paragraph))),revisionId
```

This retrieves:
- The document title
- Paragraph content from the body object across all tabs
- The revision ID

### Python Example

```python
# Get only specific fields
result = service.documents().get(
    documentId=DOCUMENT_ID,
    fields='title,tabs(documentTab(body.content(paragraph))),revisionId'
).execute()

print(f"Title: {result.get('title')}")
print(f"Revision ID: {result.get('revisionId')}")
```

See @performance.md for more on optimizing API requests.

## Updating with Field Masks

During batch update operations, field masks indicate which fields are being modified. Fields absent from the mask retain their current values.

You can also clear a field by including it in the mask without specifying a value in the updated message.

### Example: Update Text Style

```python
requests = [{
    'updateTextStyle': {
        'range': {'startIndex': 1, 'endIndex': 10, 'tabId': TAB_ID},
        'textStyle': {
            'bold': True,
            'foregroundColor': {
                'color': {'rgbColor': {'blue': 1.0}}
            }
        },
        # Only bold and foregroundColor will be updated
        # Other text style properties remain unchanged
        'fields': 'bold,foregroundColor'
    }
}]
```

### Example: Update Paragraph Style

```python
requests = [{
    'updateParagraphStyle': {
        'range': {'startIndex': 1, 'endIndex': 50, 'tabId': TAB_ID},
        'paragraphStyle': {
            'namedStyleType': 'HEADING_1',
            'spaceAbove': {'magnitude': 10, 'unit': 'PT'}
        },
        # Only namedStyleType and spaceAbove will be updated
        'fields': 'namedStyleType,spaceAbove'
    }
}]
```

See @format-text.md for complete formatting examples.

## Important Guidelines

**Avoid wildcard (`*`) syntax in production.** Wildcards can produce unwanted results if the API is updated in the future, as read-only fields and newly added fields may cause errors. Always explicitly list specific fields being updated.

### Good Practice

```python
'fields': 'bold,italic,foregroundColor'
```

### Avoid in Production

```python
'fields': '*'  # Don't use wildcards
```

## Common Field Mask Patterns

### Text Style Fields

```
bold, italic, underline, strikethrough, smallCaps,
backgroundColor, foregroundColor, fontSize,
weightedFontFamily, baselineOffset, link
```

### Paragraph Style Fields

```
namedStyleType, alignment, lineSpacing, direction,
spaceAbove, spaceBelow, borderBetween, borderTop,
borderBottom, borderLeft, borderRight, indentFirstLine,
indentStart, indentEnd, keepLinesTogether, keepWithNext,
avoidWidowAndOrphan, shading
```

### Table Column Properties Fields

```
widthType, width
```

### Table Row Style Fields

```
minRowHeight
```
