# Work with Suggestions

Google Docs enables collaborators to make suggestions that function as deferred edits awaiting approval. When retrieving document content via the `documents.get` method, responses may include unresolved suggestions.

## Controlling Suggestion Display

The optional `suggestionsViewMode` parameter controls how suggestions appear in API responses:

- **SUGGESTIONS_INLINE**: Text pending deletion or insertion displays within the document
- **PREVIEW_SUGGESTIONS_ACCEPTED**: Shows a preview with all suggestions accepted
- **PREVIEW_WITHOUT_SUGGESTIONS**: Shows a preview with all suggestions rejected

If omitted, the API applies a default mode appropriate to the user's access level.

## Index Considerations

The `suggestionsViewMode` significantly impacts response indexes. To obtain indexes that you can use in a subsequent `documents.batchUpdate` call, get the version using **SUGGESTIONS_INLINE**. Only this mode provides the correct indexes.

This matters because suggested insertions and deletions shift text positions, altering the start and end index values for subsequent elements.

See @structure.md for understanding how indexes work.

## Style Suggestions

Beyond text changes, documents support style suggestions—proposed formatting modifications. These differ from content changes in that they:

- Don't offset indexes (though may fragment TextRun objects)
- Add annotations about suggested style changes via `SuggestedTextStyle`

Style suggestions contain:
- `textStyle`: The formatting after applying the suggestion
- `textStyleSuggestionState`: Indicates which specific style properties changed

Only properties marked `true` in `textStyleSuggestionState` constitute the actual suggestion.

See @format-text.md for text styling details.

## Code Examples

### Python

```python
# Get document with suggestions inline (for correct indexes)
SUGGEST_MODE = 'SUGGESTIONS_INLINE'
result = service.documents().get(
    documentId=DOCUMENT_ID,
    includeTabsContent=True,
    suggestionsViewMode=SUGGEST_MODE
).execute()

# Access suggestions from the response
for tab in result.get('tabs', []):
    document_tab = tab.get('documentTab', {})
    body = document_tab.get('body', {})

    for content in body.get('content', []):
        paragraph = content.get('paragraph', {})
        for element in paragraph.get('elements', []):
            text_run = element.get('textRun', {})

            # Check for suggested insertions
            if 'suggestedInsertionIds' in text_run:
                print(f"Suggested insertion: {text_run.get('content')}")

            # Check for suggested deletions
            if 'suggestedDeletionIds' in text_run:
                print(f"Suggested deletion: {text_run.get('content')}")
```

### Getting Preview Without Suggestions

```python
# Get document preview without suggestions
SUGGEST_MODE = 'PREVIEW_WITHOUT_SUGGESTIONS'
result = service.documents().get(
    documentId=DOCUMENT_ID,
    includeTabsContent=True,
    suggestionsViewMode=SUGGEST_MODE
).execute()
```

### Getting Preview With Suggestions Accepted

```python
# Get document preview with all suggestions accepted
SUGGEST_MODE = 'PREVIEW_SUGGESTIONS_ACCEPTED'
result = service.documents().get(
    documentId=DOCUMENT_ID,
    includeTabsContent=True,
    suggestionsViewMode=SUGGEST_MODE
).execute()
```

## Notes

- The API does not provide methods to accept or reject suggestions programmatically
- Suggestions are read-only through the API—you can view them but not resolve them
- When performing batch updates, always use `SUGGESTIONS_INLINE` mode to get accurate indexes
