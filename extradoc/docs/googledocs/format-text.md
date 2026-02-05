# Format Text

The Google Docs API enables developers to apply two distinct formatting categories to document text:

1. **Character formatting** — modifications to individual text properties such as font, color, and text decoration
2. **Paragraph formatting** — modifications to text block properties including indentation and line spacing

## Character Formatting

Character formatting controls how individual text characters display in a document. When you apply character formatting, it supersedes the default styling inherited from the paragraph's TextStyle. Any character properties left unspecified continue inheriting from the paragraph style.

See @structure.md for details on style inheritance.

### Implementation

Use the `batchUpdate` method with `UpdateTextStyleRequest` to modify character formatting. You must provide a Range object containing:

- `segmentId` — identifies which section (header, footer, footnote, or body) contains the text
- `startIndex` and `endIndex` — define the text span to format
- `tabId` — specifies which tab holds the text (see @tabs.md)

### Example Operations

The following demonstrates applying multiple formatting changes:

- Making characters 1-5 bold and italic
- Formatting characters 6-10 with blue color and 14-point Times New Roman font
- Hyperlinking characters 11-15 to a URL

### Java

```java
List<Request> requests = new ArrayList<>();

// Bold and italic for characters 1-5
requests.add(new Request().setUpdateTextStyle(new UpdateTextStyleRequest()
    .setRange(new Range().setStartIndex(1).setEndIndex(5).setTabId(TAB_ID))
    .setTextStyle(new TextStyle().setBold(true).setItalic(true))
    .setFields("bold,italic")));

// Blue 14pt Times New Roman for characters 6-10
requests.add(new Request().setUpdateTextStyle(new UpdateTextStyleRequest()
    .setRange(new Range().setStartIndex(6).setEndIndex(10).setTabId(TAB_ID))
    .setTextStyle(new TextStyle()
        .setWeightedFontFamily(new WeightedFontFamily().setFontFamily("Times New Roman"))
        .setFontSize(new Dimension().setMagnitude(14.0).setUnit("PT"))
        .setForegroundColor(new OptionalColor().setColor(new Color()
            .setRgbColor(new RgbColor().setBlue(1.0).setGreen(0.0).setRed(0.0)))))
    .setFields("weightedFontFamily,fontSize,foregroundColor")));

// Hyperlink for characters 11-15
requests.add(new Request().setUpdateTextStyle(new UpdateTextStyleRequest()
    .setRange(new Range().setStartIndex(11).setEndIndex(15).setTabId(TAB_ID))
    .setTextStyle(new TextStyle().setLink(new Link().setUrl("https://www.example.com")))
    .setFields("link")));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [
    # Bold and italic for characters 1-5
    {
        'updateTextStyle': {
            'range': {'startIndex': 1, 'endIndex': 5, 'tabId': TAB_ID},
            'textStyle': {'bold': True, 'italic': True},
            'fields': 'bold,italic'
        }
    },
    # Blue 14pt Times New Roman for characters 6-10
    {
        'updateTextStyle': {
            'range': {'startIndex': 6, 'endIndex': 10, 'tabId': TAB_ID},
            'textStyle': {
                'weightedFontFamily': {'fontFamily': 'Times New Roman'},
                'fontSize': {'magnitude': 14, 'unit': 'PT'},
                'foregroundColor': {
                    'color': {'rgbColor': {'blue': 1.0, 'green': 0.0, 'red': 0.0}}
                }
            },
            'fields': 'weightedFontFamily,fontSize,foregroundColor'
        }
    },
    # Hyperlink for characters 11-15
    {
        'updateTextStyle': {
            'range': {'startIndex': 11, 'endIndex': 15, 'tabId': TAB_ID},
            'textStyle': {'link': {'url': 'https://www.example.com'}},
            'fields': 'link'
        }
    }
]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## Paragraph Formatting

Paragraph formatting determines how text blocks render, including alignment, indentation, spacing, and borders. Like character formatting, applied properties override style inheritance while unspecified properties inherit from the underlying paragraph style.

### Implementation

Use `UpdateParagraphStyleRequest` to modify paragraph-level properties.

### Example Operations

The following shows configuring:

- Named style assignment (e.g., "HEADING_1")
- Custom spacing above and below paragraphs
- Left border with custom color, dash style, padding, and width

### Java

```java
List<Request> requests = new ArrayList<>();

requests.add(new Request().setUpdateParagraphStyle(new UpdateParagraphStyleRequest()
    .setRange(new Range().setStartIndex(1).setEndIndex(50).setTabId(TAB_ID))
    .setParagraphStyle(new ParagraphStyle()
        .setNamedStyleType("HEADING_1")
        .setSpaceAbove(new Dimension().setMagnitude(10.0).setUnit("PT"))
        .setSpaceBelow(new Dimension().setMagnitude(10.0).setUnit("PT"))
        .setBorderLeft(new ParagraphBorder()
            .setColor(new OptionalColor().setColor(new Color()
                .setRgbColor(new RgbColor().setBlue(1.0).setGreen(0.0).setRed(0.0))))
            .setDashStyle("SOLID")
            .setPadding(new Dimension().setMagnitude(5.0).setUnit("PT"))
            .setWidth(new Dimension().setMagnitude(2.0).setUnit("PT"))))
    .setFields("namedStyleType,spaceAbove,spaceBelow,borderLeft")));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [
    {
        'updateParagraphStyle': {
            'range': {'startIndex': 1, 'endIndex': 50, 'tabId': TAB_ID},
            'paragraphStyle': {
                'namedStyleType': 'HEADING_1',
                'spaceAbove': {'magnitude': 10, 'unit': 'PT'},
                'spaceBelow': {'magnitude': 10, 'unit': 'PT'},
                'borderLeft': {
                    'color': {'color': {'rgbColor': {'blue': 1.0, 'green': 0.0, 'red': 0.0}}},
                    'dashStyle': 'SOLID',
                    'padding': {'magnitude': 5, 'unit': 'PT'},
                    'width': {'magnitude': 2, 'unit': 'PT'}
                }
            },
            'fields': 'namedStyleType,spaceAbove,spaceBelow,borderLeft'
        }
    }
]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

See @field-masks.md for details on the `fields` parameter usage.
