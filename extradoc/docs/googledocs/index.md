# Google Docs API Documentation

This documentation covers the Google Docs API from the perspective of building a tool that:
1. **Reads** a Google Doc and converts it to HTML
2. **Diffs** the original HTML against modified HTML
3. **Generates** batchUpdate requests to apply those changes

## Quick Navigation

### Understanding Document Structure

Start here to understand how Google Docs are organized internally.

| Document | Purpose |
|----------|---------|
| [structure.md](structure.md) | How documents are structured (Body, Paragraphs, TextRuns) |
| [tabs.md](tabs.md) | Working with document tabs |
| [document.md](document.md) | Document resource and API methods overview |

### Reading Documents (documents.get)

To convert a Google Doc to HTML, you need to understand what `documents.get` returns.

| Document | Purpose |
|----------|---------|
| [requests-and-responses.md](requests-and-responses.md) | API methods (get, create, batchUpdate) |
| [suggestions.md](suggestions.md) | Handling suggested changes in responses |
| [field-masks.md](field-masks.md) | Requesting specific fields for efficiency |

### Writing Changes (documents.batchUpdate)

To apply changes from an HTML diff, you need to generate batchUpdate requests.

| Document | Purpose |
|----------|---------|
| [batch.md](batch.md) | How batch requests work |
| [rules-behavior.md](rules-behavior.md) | Constraints and limitations on edits |
| [best-practices.md](best-practices.md) | Edit backwards, handle collaboration |

### Content Operations

| Document | Purpose |
|----------|---------|
| [move-text.md](move-text.md) | Insert, delete, and move text |
| [format-text.md](format-text.md) | Character and paragraph formatting |
| [lists.md](lists.md) | Create and remove bullet lists |
| [tables.md](tables.md) | Table operations (insert, delete, modify) |
| [images.md](images.md) | Insert inline images |
| [named-ranges.md](named-ranges.md) | Named ranges for tracking content |
| [merge.md](merge.md) | Template merging with ReplaceAllText |

### Reference

| Document | Purpose |
|----------|---------|
| [documents.md](documents.md) | Create and manage documents |
| [performance.md](performance.md) | Optimization techniques |
| [api/](api/index.md) | API schema reference (extracted from discovery doc) |

---

## Core Concepts

### Document ID

Every Google Doc has a unique `documentId` that can be extracted from its URL:

```
https://docs.google.com/document/d/DOCUMENT_ID/edit
```

Use regex pattern `/document/d/([a-zA-Z0-9-_]+)` to extract it.

### Indexes

All content positions use **UTF-16 code unit indexes**. Surrogate pairs (emoji, etc.) consume two index units. When working with text:
- `startIndex` marks where content begins
- `endIndex` marks where content ends (exclusive)

### Document Hierarchy

```
Document
└── tabs[]
    └── Tab
        └── documentTab (DocumentTab)
            └── body (Body)
                └── content[] (StructuralElement)
                    ├── paragraph (Paragraph)
                    │   └── elements[] (ParagraphElement)
                    │       └── textRun (TextRun)
                    │           ├── content: "Hello World"
                    │           └── textStyle: {bold: true, ...}
                    └── table (Table)
                        └── tableRows[]
                            └── tableCells[]
                                └── content[] (recursive)
```

See [api/Document.md](api/Document.md) for the complete schema.

### The batchUpdate Pattern

All modifications go through `documents.batchUpdate`, which accepts an array of request objects:

```python
requests = [
    {'insertText': {'location': {'index': 1}, 'text': 'Hello'}},
    {'updateTextStyle': {'range': {...}, 'textStyle': {...}, 'fields': '...'}}
]
service.documents().batchUpdate(documentId=DOC_ID, body={'requests': requests}).execute()
```

Key points:
- Requests are processed **in order**
- All requests are **atomic** (all succeed or all fail)
- **Edit backwards** (highest index first) to avoid recalculating positions

See [api/Request.md](api/Request.md) for all available request types.

---

## Workflow: Reading a Document

1. Call `documents.get(documentId, includeTabsContent=True)`
2. Navigate to `document.tabs[0].documentTab.body.content`
3. Iterate through `StructuralElement` objects
4. For paragraphs, iterate through `elements` to get `TextRun` objects
5. Each `TextRun` has `content` (text) and `textStyle` (formatting)

See [structure.md](structure.md) for details.

## Workflow: Applying Changes

1. Read the document to get current state and `revisionId`
2. Compare original HTML with modified HTML to identify changes
3. Generate appropriate request objects for each change
4. Sort requests by index descending (edit backwards)
5. Call `batchUpdate` with `writeControl.requiredRevisionId`

See [batch.md](batch.md) and [best-practices.md](best-practices.md) for details.

---

## Common Request Types

| Operation | Request Type | See |
|-----------|--------------|-----|
| Insert text | `InsertTextRequest` | [move-text.md](move-text.md) |
| Delete content | `DeleteContentRangeRequest` | [move-text.md](move-text.md) |
| Find/replace | `ReplaceAllTextRequest` | [merge.md](merge.md) |
| Bold/italic/color | `UpdateTextStyleRequest` | [format-text.md](format-text.md) |
| Headings/alignment | `UpdateParagraphStyleRequest` | [format-text.md](format-text.md) |
| Create bullets | `CreateParagraphBulletsRequest` | [lists.md](lists.md) |
| Insert table | `InsertTableRequest` | [tables.md](tables.md) |
| Insert image | `InsertInlineImageRequest` | [images.md](images.md) |

For complete request schemas, see [api/index.md](api/index.md).
