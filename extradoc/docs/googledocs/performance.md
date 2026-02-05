# Improve Performance

This guide presents techniques to enhance your application's performance when working with the Google Docs API.

## Compression Using gzip

Reducing bandwidth per request is achievable through gzip compression. Although decompression requires additional CPU resources, the network cost savings typically justify this trade-off.

To receive gzip-encoded responses, two requirements must be met:

1. Set an `Accept-Encoding` header
2. Modify your user agent to include the string `gzip`

### Example HTTP Headers

```
Accept-Encoding: gzip
User-Agent: my program (gzip)
```

### Python Example

```python
import httplib2

http = httplib2.Http()
http.force_exception_to_status_code = True

# Enable gzip compression
headers = {
    'Accept-Encoding': 'gzip',
    'User-Agent': 'my-app (gzip)'
}
```

## Working with Partial Resources

Performance improves by requesting only necessary data portions. This approach conserves network bandwidth, CPU cycles, and memory by avoiding unnecessary field transfers, parsing, and storage.

### Partial Response

By default, servers return complete resource representations. For better performance, specify only needed fields using the `fields` request parameter to receive a "partial response."

See @field-masks.md for detailed field mask syntax.

### Basic Syntax

| Pattern | Description |
|---------|-------------|
| `fields=field1,field2` | Comma-separated fields |
| `fields=a/b` or `fields=a/b/c` | Nested fields using slash notation |
| `fields=items(id,author/email)` | Sub-selectors for specific sub-fields |
| `fields=items/pagemap/*` | Wildcards to select all items (avoid in production) |

### Example: Full vs Partial Request

**Full request (no field mask):**
```
GET https://docs.googleapis.com/v1/documents/DOCUMENT_ID
```

**Partial response request:**
```
GET https://docs.googleapis.com/v1/documents/DOCUMENT_ID?fields=title,revisionId,tabs(documentTab(body(content(paragraph(elements(textRun(content)))))))
```

### Python Example

```python
# Full document (larger response)
full_doc = service.documents().get(documentId=DOCUMENT_ID).execute()

# Partial document (smaller, faster response)
partial_doc = service.documents().get(
    documentId=DOCUMENT_ID,
    fields='title,revisionId,tabs(documentTab(body(content(paragraph))))'
).execute()
```

### Response Comparison

**Full response:** Contains all document fields, styling information, named ranges, etc.

**Partial response:**
```json
{
  "title": "My Document",
  "revisionId": "...",
  "tabs": [{
    "documentTab": {
      "body": {
        "content": [{
          "paragraph": {
            "elements": [{
              "textRun": {"content": "Hello World"}
            }]
          }
        }]
      }
    }
  }]
}
```

### Error Handling

Valid requests return HTTP `200 OK` with requested data. Invalid `fields` parameters receive HTTP `400 Bad Request` responses with descriptive error messages.

## Batch Requests

Combine multiple operations into a single API call to reduce network round trips.

See @batch.md for batch request patterns.

## Pagination

When working with large documents or listing operations, combine partial responses with pagination parameters (`maxResults`, `nextPageToken`) to fully realize performance improvements.

## Summary of Best Practices

1. **Use gzip compression** for large responses
2. **Request only needed fields** using the `fields` parameter
3. **Batch multiple operations** into single API calls
4. **Use pagination** for large datasets
5. **Cache document state** when making multiple related calls
6. **Edit backwards** to avoid index recalculation (see @best-practices.md)
