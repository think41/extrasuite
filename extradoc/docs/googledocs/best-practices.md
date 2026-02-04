# Best Practices

This documentation outlines core principles for optimal Google Docs API usage.

## 1. Edit Backwards for Efficiency

Within a single `documents.batchUpdate` call, order requests in descending order by index location to avoid recalculating index changes from insertions and deletions.

### Why This Matters

When you insert text at index 10, all content after index 10 shifts. If you then need to insert at index 20, you'd need to account for the shift. By working backwards (inserting at index 20 first, then index 10), earlier insertions don't affect later ones.

### Example

```python
# CORRECT: Edit backwards (highest index first)
requests = [
    {'insertText': {'location': {'index': 100, 'tabId': TAB_ID}, 'text': 'Third'}},
    {'insertText': {'location': {'index': 50, 'tabId': TAB_ID}, 'text': 'Second'}},
    {'insertText': {'location': {'index': 10, 'tabId': TAB_ID}, 'text': 'First'}}
]

# INCORRECT: Would require index recalculation
requests = [
    {'insertText': {'location': {'index': 10, 'tabId': TAB_ID}, 'text': 'First'}},
    # Now index 50 is actually 50 + len('First')
    {'insertText': {'location': {'index': 50, 'tabId': TAB_ID}, 'text': 'Second'}},
    # Now index 100 is shifted by both previous insertions
    {'insertText': {'location': {'index': 100, 'tabId': TAB_ID}, 'text': 'Third'}}
]
```

See @move-text.md for text manipulation examples.

## 2. Plan for Collaboration

Document state can change between API calls as other users make edits. This requires defensive programming to maintain consistency, even when collaboration isn't anticipated.

### Key Considerations

- Always fetch the latest document state before making edits
- Use `WriteControl` to detect or handle concurrent modifications
- Design operations to be idempotent where possible
- Handle revision conflicts gracefully

## 3. Ensure State Consistency Using WriteControl

The `WriteControl` field manages competing changes through two options:

### requiredRevisionId

Prevents writes if the document was modified since the read operation. Use this when you need strict consistency.

```python
# Fetch document and get revision ID
doc = service.documents().get(documentId=DOCUMENT_ID).execute()
revision_id = doc.get('revisionId')

# Make updates with revision check
body = {
    'requests': requests,
    'writeControl': {
        'requiredRevisionId': revision_id
    }
}

try:
    response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
except Exception as e:
    # Handle conflict - document was modified
    print("Document was modified by another user, refetch and retry")
```

### targetRevisionId

Merges write requests with collaborator changes into a new revision. Use this when you want to allow concurrent edits.

```python
body = {
    'requests': requests,
    'writeControl': {
        'targetRevisionId': revision_id
    }
}

response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## 4. Take Tabs into Account

Documents can contain multiple tabs requiring specific handling.

### Reading All Tabs

Set `includeTabsContent` to `true` in `documents.get()` to retrieve all tab content:

```python
doc = service.documents().get(
    documentId=DOCUMENT_ID,
    includeTabsContent=True
).execute()

# Iterate through all tabs
for tab in doc.get('tabs', []):
    tab_id = tab.get('tabProperties', {}).get('tabId')
    document_tab = tab.get('documentTab', {})
    body = document_tab.get('body', {})
    # Process tab content...
```

### Writing to Specific Tabs

Specify tab IDs in `documents.batchUpdate()` requests; requests default to the first tab if unspecified:

```python
requests = [{
    'insertText': {
        'location': {
            'index': 1,
            'tabId': 'specific-tab-id'  # Target specific tab
        },
        'text': 'Hello World'
    }
}]
```

See @tabs.md for complete tab handling documentation.

## 5. Use Field Masks for Updates

Always specify exactly which fields you're updating to avoid unintended changes:

```python
requests = [{
    'updateTextStyle': {
        'range': {'startIndex': 1, 'endIndex': 10, 'tabId': TAB_ID},
        'textStyle': {'bold': True},
        'fields': 'bold'  # Only update bold, leave other styles unchanged
    }
}]
```

See @field-masks.md for field mask patterns.

## 6. Batch Operations for Efficiency

Group related operations into single `batchUpdate` calls:

```python
# GOOD: Single API call
requests = [
    {'insertText': {...}},
    {'updateTextStyle': {...}},
    {'createParagraphBullets': {...}}
]
service.documents().batchUpdate(documentId=DOCUMENT_ID, body={'requests': requests}).execute()

# AVOID: Multiple API calls
service.documents().batchUpdate(documentId=DOCUMENT_ID, body={'requests': [{'insertText': {...}}]}).execute()
service.documents().batchUpdate(documentId=DOCUMENT_ID, body={'requests': [{'updateTextStyle': {...}}]}).execute()
service.documents().batchUpdate(documentId=DOCUMENT_ID, body={'requests': [{'createParagraphBullets': {...}}]}).execute()
```

See @batch.md for batch request details.

## 7. Request Only What You Need

Use partial responses to improve performance:

```python
# Only get title and body content
doc = service.documents().get(
    documentId=DOCUMENT_ID,
    fields='title,tabs(documentTab(body))'
).execute()
```

See @performance.md for performance optimization techniques.
