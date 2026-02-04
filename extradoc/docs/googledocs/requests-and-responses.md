# Requests and Responses

The Google Docs API supports HTTP requests and language-specific client library methods that are functionally equivalent. The API returns HTTP responses containing request results, with language-specific formatting when using client libraries.

## Request Methods

The Docs API provides three primary methods:

1. **`documents.create`** - Creates a new blank Google Docs document
2. **`documents.get`** - Returns a complete document instance with content, formatting, and features
3. **`documents.batchUpdate`** - Submits multiple editing requests to apply atomically and returns results

The `documents.get` and `documents.batchUpdate` methods require a `documentId` parameter. The `documents.create` method returns the created document's ID for reference.

**Important limitation:** Published documents cannot be retrieved using `documents.get`, as they use a different URL format. Attempting to use the new `documentId` returns a 404 error. As a workaround, use the Drive API to copy the published document to access it instead.

## Batch Updates

The `documents.batchUpdate` method accepts a list of request objects, each specifying a single operation (such as formatting or inserting images). Requests are validated and processed in order.

**Atomic processing:** All requests apply atomically—if any request fails, the entire batch fails and no changes occur.

Some `batchUpdate` methods return response bodies containing response objects indexed to match corresponding requests. Other requests return empty replies.

See @batch.md for detailed batch request patterns.

### Batch Update Operations

The API supports various request types organized by category:

**Text Operations:**
- `InsertTextRequest` - See @move-text.md
- `ReplaceAllTextRequest` - See @merge.md
- `DeleteContentRangeRequest` - See @move-text.md

**Style Operations:**
- `CreateParagraphBulletsRequest` - See @lists.md
- `UpdateTextStyleRequest` - See @format-text.md
- `UpdateParagraphStyleRequest` - See @format-text.md
- `UpdateTableColumnPropertiesRequest` - See @tables.md
- `UpdateDocumentStyleRequest`
- `UpdateSectionStyleRequest`

**Named Ranges:**
- `CreateNamedRangeRequest` - See @named-ranges.md
- `ReplaceNamedRangeContentRequest` - See @named-ranges.md
- `DeleteNamedRangeRequest` - See @named-ranges.md

**Images:**
- `InsertInlineImageRequest` - See @images.md
- `ReplaceImageRequest`

**Tables:**
- Insert/update/delete operations for tables, rows, and columns - See @tables.md

**Page Objects:**
- Insert page breaks, headers, footers, footnotes, section breaks
- Delete positioned objects

Grouping multiple requests via `batchUpdate` conserves quota and improves performance. See @performance.md for optimization tips.
