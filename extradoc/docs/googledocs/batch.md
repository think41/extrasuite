# Batch Requests

The Google Docs API allows you to combine multiple requests into a single batch operation, reducing network overhead and improving application performance. Each batch request counts as one API call toward your usage limits, regardless of how many subrequests it contains.

## Key Benefits

Batching is particularly useful when:
- Uploading large amounts of data initially
- Updating metadata or formatting across multiple objects
- Deleting many objects simultaneously

## Important Considerations

**Authentication & Limits:** A batch request is authenticated once, with that single authentication applying to all subrequests. The server processes subrequests sequentially, allowing later requests to depend on actions from earlier ones.

**Atomicity:** All subrequests are applied atomically—if any request fails validation, the entire batch operation is unsuccessful and no changes are applied.

**Responses:** Some requests return response objects with metadata about applied changes (like IDs of newly created objects), while others return empty responses.

## Request Structure

A batch request uses the `batchUpdate` method with a `requests` array containing individual request objects in JSON format. Each request specifies a single operation type.

```python
body = {
    'requests': [
        {'insertText': {...}},
        {'updateTextStyle': {...}},
        {'createNamedRange': {...}}
    ]
}

response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## Response Structure

The server returns a `replies` array with responses in the same index order as the corresponding requests. Empty objects appear for requests without responses.

```python
# Response structure
{
    'replies': [{}, {}, {'createNamedRange': {'namedRangeId': '...'}}],
    'writeControl': {'requiredRevisionId': '...'},
    'documentId': '...'
}
```

## Complete Example

Insert "Hello World" text, then format the word "Hello" as bold blue text:

### Request

```python
requests = [
    {
        'insertText': {
            'location': {'index': 1, 'tabId': TAB_ID},
            'text': 'Hello World'
        }
    },
    {
        'updateTextStyle': {
            'range': {'startIndex': 1, 'endIndex': 6, 'tabId': TAB_ID},
            'textStyle': {
                'bold': True,
                'foregroundColor': {
                    'color': {'rgbColor': {'blue': 1.0}}
                }
            },
            'fields': 'bold,foregroundColor'
        }
    }
]

body = {
    'requests': requests,
    'writeControl': {'requiredRevisionId': REQUIRED_REVISION_ID}
}

response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

### Response

```json
{
  "replies": [{}, {}],
  "writeControl": {"requiredRevisionId": "REQUIRED_REVISION_ID"},
  "documentId": "DOCUMENT_ID"
}
```

## Request Ordering

Since requests are processed sequentially within a batch, order matters. For optimal performance when inserting or deleting content, work backwards from the end of the document to avoid recalculating indexes.

See @best-practices.md for the backward-editing pattern.

## Write Control

Use `WriteControl` to manage concurrent edits:

- `requiredRevisionId`: Fails if document was modified since read
- `targetRevisionId`: Merges changes with collaborator edits

See @best-practices.md for details on handling collaboration.

## Combining Different Operations

A single batch can combine various operation types:

```python
requests = [
    # Insert text
    {'insertText': {'location': {'index': 1, 'tabId': TAB_ID}, 'text': 'Title\n'}},

    # Format as heading
    {'updateParagraphStyle': {
        'range': {'startIndex': 1, 'endIndex': 7, 'tabId': TAB_ID},
        'paragraphStyle': {'namedStyleType': 'HEADING_1'},
        'fields': 'namedStyleType'
    }},

    # Insert a table
    {'insertTable': {
        'rows': 3,
        'columns': 3,
        'endOfSegmentLocation': {'tabId': TAB_ID}
    }},

    # Create a named range
    {'createNamedRange': {
        'name': 'title_section',
        'range': {'startIndex': 1, 'endIndex': 7, 'tabId': TAB_ID}
    }}
]
```

See @requests-and-responses.md for the complete list of available request types.
