# Insert, Delete, and Move Text

The Google Docs API enables developers to manipulate text content within documents through insertion, deletion, and relocation operations. These actions can be performed across any document segment including the body, headers, footers, and footnotes.

## Insert Text

To add text to a document, use the `documents.batchUpdate` method with an `InsertTextRequest` that specifies both the text content and its target location.

**Key consideration:** All indexes use UTF-16 code units.

### Index Management Strategy

When performing multiple insertions, each operation shifts all subsequent indexes. The recommended approach: **do the insertion at the highest-numbered index first, working your way towards the beginning.**

This backward-writing technique eliminates the need to recalculate offset positions after each operation. See @best-practices.md for more on this pattern.

### Java

```java
List<Request> requests = new ArrayList<>();
requests.add(new Request().setInsertText(
    new InsertTextRequest()
        .setText("Hello World")
        .setLocation(new Location().setIndex(1).setTabId(TAB_ID))));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [
    {
        'insertText': {
            'location': {'index': 1, 'tabId': TAB_ID},
            'text': 'Hello World'
        }
    }
]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

### PHP

```php
$requests = [
    new Google_Service_Docs_Request([
        'insertText' => [
            'location' => ['index' => 1, 'tabId' => $tabId],
            'text' => 'Hello World'
        ]
    ])
];

$batchUpdateRequest = new Google_Service_Docs_BatchUpdateDocumentRequest([
    'requests' => $requests
]);
$response = $service->documents->batchUpdate($documentId, $batchUpdateRequest);
```

## Delete Text

Text removal requires constructing a Range object defining the start and end indexes, then using `DeleteContentRangeRequest` with the `documents.batchUpdate` method.

The same backward-writing optimization applies: process deletions from highest to lowest indexes to avoid recalculating positions.

### Java

```java
List<Request> requests = new ArrayList<>();
requests.add(new Request().setDeleteContentRange(
    new DeleteContentRangeRequest()
        .setRange(new Range()
            .setStartIndex(1)
            .setEndIndex(10)
            .setTabId(TAB_ID))));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [
    {
        'deleteContentRange': {
            'range': {
                'startIndex': 1,
                'endIndex': 10,
                'tabId': TAB_ID
            }
        }
    }
]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## Move Text

Moving text involves a two-step process: extract the content from its current location, then insert it elsewhere. The API provides no clipboard mechanism, so you must first retrieve the text before relocating it.

See @rules-behavior.md for constraints on text operations.
