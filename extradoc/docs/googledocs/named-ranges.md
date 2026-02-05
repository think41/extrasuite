# Work with Named Ranges

The Google Docs API enables developers to use named ranges to streamline editing operations. A named range identifies a specific document section that can be referenced later, with indexes automatically updating as content changes, eliminating the need to manually track edits.

## Key Concepts

### What Named Ranges Do

Named ranges mark document sections for later reference. As users add or remove content, the indexes adjust automatically, simplifying text location and updating tasks without manual searching.

### Example Use Case

If you designate a named range for a "product description" section, you can later retrieve its start and end indexes and replace the text between those points with new content.

## Important Limitations

- Named ranges are not private—anyone with API access can view the definition
- Named ranges reference original content only; duplicating and inserting that content elsewhere preserves the range reference to the original location only

## Creating a Named Range

Use `CreateNamedRangeRequest` to create a named range.

```python
requests = [{
    'createNamedRange': {
        'name': 'product_description',
        'range': {
            'startIndex': 10,
            'endIndex': 50,
            'tabId': TAB_ID
        }
    }
}]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()

# The response contains the created named range ID
named_range_id = response.get('replies')[0].get('createNamedRange').get('namedRangeId')
```

## Replacing Named Range Contents

The process involves:

1. Fetching the document to determine current named range indexes
2. Locating the matching named range in the specified tab
3. Deleting existing content within the range
4. Inserting replacement text
5. Recreating the named range on the new text
6. Executing a batch update with revision control

### Java

```java
// Fetch document to get current state
Document doc = docsService.documents().get(DOCUMENT_ID)
    .setIncludeTabsContent(true).execute();

// Find the named range
NamedRanges namedRanges = doc.getTabs().get(0).getDocumentTab().getNamedRanges()
    .get("product_description");
NamedRange namedRange = namedRanges.getNamedRanges().get(0);
Range range = namedRange.getRanges().get(0);

List<Request> requests = new ArrayList<>();

// Delete the named range definition
requests.add(new Request().setDeleteNamedRange(
    new DeleteNamedRangeRequest().setNamedRangeId(namedRange.getNamedRangeId())));

// Delete the content
requests.add(new Request().setDeleteContentRange(
    new DeleteContentRangeRequest().setRange(range)));

// Insert new content
String newText = "Updated product description";
requests.add(new Request().setInsertText(
    new InsertTextRequest()
        .setText(newText)
        .setLocation(new Location()
            .setIndex(range.getStartIndex())
            .setTabId(TAB_ID))));

// Recreate the named range
requests.add(new Request().setCreateNamedRange(
    new CreateNamedRangeRequest()
        .setName("product_description")
        .setRange(new Range()
            .setStartIndex(range.getStartIndex())
            .setEndIndex(range.getStartIndex() + newText.length())
            .setTabId(TAB_ID))));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest()
    .setRequests(requests)
    .setWriteControl(new WriteControl().setRequiredRevisionId(doc.getRevisionId()));

BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
# Fetch document to get current state
doc = service.documents().get(
    documentId=DOCUMENT_ID,
    includeTabsContent=True
).execute()

# Find the named range
document_tab = doc['tabs'][0]['documentTab']
named_ranges = document_tab.get('namedRanges', {}).get('product_description', {})
named_range = named_ranges.get('namedRanges', [{}])[0]
range_info = named_range.get('ranges', [{}])[0]
start_index = range_info.get('startIndex')
end_index = range_info.get('endIndex')

new_text = 'Updated product description'

requests = [
    # Delete the named range definition
    {'deleteNamedRange': {'namedRangeId': named_range.get('namedRangeId')}},
    # Delete the content
    {'deleteContentRange': {'range': range_info}},
    # Insert new content
    {'insertText': {
        'text': new_text,
        'location': {'index': start_index, 'tabId': TAB_ID}
    }},
    # Recreate the named range
    {'createNamedRange': {
        'name': 'product_description',
        'range': {
            'startIndex': start_index,
            'endIndex': start_index + len(new_text),
            'tabId': TAB_ID
        }
    }}
]

body = {
    'requests': requests,
    'writeControl': {'requiredRevisionId': doc.get('revisionId')}
}

response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## Deleting a Named Range

Use `DeleteNamedRangeRequest` to remove a named range definition (this does not delete the content).

```python
requests = [{
    'deleteNamedRange': {
        'namedRangeId': NAMED_RANGE_ID
    }
}]
```

This approach supports working with tabs; the code can be extended to iterate across multiple tabs as needed. See @tabs.md for working with multiple tabs.

See @best-practices.md for using `WriteControl` to handle concurrent edits.
