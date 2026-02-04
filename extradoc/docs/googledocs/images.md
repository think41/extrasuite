# Insert Inline Images

The Google Docs API enables developers to insert images into documents programmatically using the `InsertInlineImageRequest` method. Images must be publicly accessible through the URL provided in the request, and developers can optionally resize images using the `objectSize` field.

## Requirements

Images must satisfy specific requirements:
- Under 50 MB file size
- Not exceeding 25 megapixels
- PNG, JPEG, or GIF format
- Image URI must be publicly accessible and under 2 KB

See @rules-behavior.md for additional constraints on image placement.

## How It Works

When executed, the method inserts an image as a new `ParagraphElement` containing an `InlineObjectElement` with a length of 1, positioned at the specified `startIndex` from the request's location.

## Code Examples

### Java

```java
List<Request> requests = new ArrayList<>();
requests.add(new Request().setInsertInlineImage(new InsertInlineImageRequest()
    .setUri("https://example.com/image.png")
    .setLocation(new Location().setIndex(1).setTabId(TAB_ID))
    .setObjectSize(new Size()
        .setHeight(new Dimension().setMagnitude(50.0).setUnit("PT"))
        .setWidth(new Dimension().setMagnitude(50.0).setUnit("PT")))));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [{
    'insertInlineImage': {
        'location': {'index': 1, 'tabId': TAB_ID},
        'uri': 'https://example.com/image.png',
        'objectSize': {
            'height': {'magnitude': 50, 'unit': 'PT'},
            'width': {'magnitude': 50, 'unit': 'PT'}
        }
    }
}]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

### PHP

```php
$requests = [
    new Google_Service_Docs_Request([
        'insertInlineImage' => [
            'location' => ['index' => 1, 'tabId' => $tabId],
            'uri' => 'https://example.com/image.png',
            'objectSize' => [
                'height' => ['magnitude' => 50, 'unit' => 'PT'],
                'width' => ['magnitude' => 50, 'unit' => 'PT']
            ]
        ]
    ])
];

$batchUpdateRequest = new Google_Service_Docs_BatchUpdateDocumentRequest([
    'requests' => $requests
]);
$response = $service->documents->batchUpdate($documentId, $batchUpdateRequest);
```

## Notes

- Dimensions are specified in points (PT)
- The image is inserted at the specified index, shifting subsequent content
- When inserting multiple images, use the backward-writing approach (see @best-practices.md)
- Images cannot be embedded within footnotes or equations
