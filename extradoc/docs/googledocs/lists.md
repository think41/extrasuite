# Work with Lists

The Google Docs API enables developers to convert plain paragraphs to bulleted lists and remove bullets from paragraphs.

## Convert a Paragraph to a List

To create a bulleted list, use the `documents.batchUpdate` method with a `CreateParagraphBulletsRequest`. This request requires:

- A `Range` specifying which cells to affect
- A `BulletGlyphPreset` determining the bullet pattern

All paragraphs overlapping the specified range become bulleted. When a range intersects a table, bullets apply within table cells. Paragraph nesting levels are determined by counting leading tabs.

**Important limitation:** You cannot adjust nesting levels of existing bullets. Instead, delete the bullet, add leading tabs, then recreate it.

You can also use this request to change bullet styles for existing lists.

See @rules-behavior.md for details on how bullet creation affects indexes.

### Java

```java
List<Request> requests = new ArrayList<>();

// First insert some text
requests.add(new Request().setInsertText(new InsertTextRequest()
    .setText("Item One\nItem Two\nItem Three\n")
    .setLocation(new Location().setIndex(1).setTabId(TAB_ID))));

// Then apply bullets to the text
requests.add(new Request().setCreateParagraphBullets(
    new CreateParagraphBulletsRequest()
        .setRange(new Range()
            .setStartIndex(1)
            .setEndIndex(30)
            .setTabId(TAB_ID))
        .setBulletPreset("BULLET_ARROW_DIAMOND_DISC")));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [
    # First insert some text
    {
        'insertText': {
            'location': {'index': 1, 'tabId': TAB_ID},
            'text': 'Item One\nItem Two\nItem Three\n',
        }
    },
    # Then apply bullets to the text
    {
        'createParagraphBullets': {
            'range': {
                'startIndex': 1,
                'endIndex': 30,
                'tabId': TAB_ID
            },
            'bulletPreset': 'BULLET_ARROW_DIAMOND_DISC',
        }
    }
]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## Available Bullet Presets

Common bullet presets include:
- `BULLET_DISC_CIRCLE_SQUARE`
- `BULLET_DIAMONDX_ARROW3D_SQUARE`
- `BULLET_CHECKBOX`
- `BULLET_ARROW_DIAMOND_DISC`
- `BULLET_STAR_CIRCLE_SQUARE`
- `BULLET_ARROW3D_CIRCLE_SQUARE`
- `BULLET_LEFTTRIANGLE_DIAMOND_DISC`
- `NUMBERED_DECIMAL_ALPHA_ROMAN`
- `NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS`
- `NUMBERED_DECIMAL_NESTED`
- `NUMBERED_UPPERALPHA_ALPHA_ROMAN`
- `NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL`
- `NUMBERED_ZERODECIMAL_ALPHA_ROMAN`

## Remove Bullets from a List

Use `documents.batchUpdate` with a `DeleteParagraphBulletsRequest` and a `Range` specifying affected cells.

This method removes all bullets overlapping the range regardless of nesting level. Indentation is automatically added to preserve visual nesting hierarchy.

### Java

```java
List<Request> requests = new ArrayList<>();
requests.add(new Request().setDeleteParagraphBullets(
    new DeleteParagraphBulletsRequest()
        .setRange(new Range()
            .setStartIndex(1)
            .setEndIndex(50)
            .setTabId(TAB_ID))));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [
    {
        'deleteParagraphBullets': {
            'range': {
                'startIndex': 1,
                'endIndex': 50,
                'tabId': TAB_ID
            },
        }
    }
]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

See @structure.md for understanding how lists fit into document structure.
