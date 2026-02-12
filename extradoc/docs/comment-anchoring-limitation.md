# Limitation: API-Created Comments Cannot Be Anchored to Text in Google Docs

## Summary

Comments created via the Google Drive API v3 cannot be anchored to specific text in Google Docs. They always appear as "Original content deleted" in the UI, regardless of the anchor format or parameters used. This is a known Google API limitation.

## Background

Google Docs comments are created through the Drive API v3 `comments.create` endpoint, not through the Docs API. The `comments` resource has three relevant fields:

- `content`: The comment text
- `anchor`: A JSON string representing the region in the file
- `quotedFileContent`: The file content the comment refers to (the highlighted text)

When a user creates a comment through the Google Docs UI by selecting text, the comment is properly anchored — it highlights the selected text and appears in the margin next to it. We attempted to replicate this behavior via the API.

## Test Setup

All tests were performed against a minimal Google Doc containing only "Hello World." (Docs API indices 1–13). A UI-created comment on this text was used as a reference.

The UI-created comment returned by the API:
```json
{
  "id": "AAABzauNR08",
  "anchor": "kix.layzbrc0c7lb",
  "quotedFileContent": {"mimeType": "text/html", "value": "Hello World."},
  "author": {"displayName": "Sripathi Krishnan"}
}
```

## Strategies Attempted

### Strategy 1: JSON anchor only (offset/length)

```json
{
  "content": "...",
  "anchor": "{\"r\":\"head\",\"a\":[{\"txt\":{\"o\":1,\"l\":12}}]}"
}
```
**Result:** "Original content deleted". The `{"r":"head","a":[{"txt":{"o":...,"l":...}}]}` format is what Google returns when *reading* API-created comments, but it does not work for *creating* them.

### Strategy 2: `quotedFileContent` only (no anchor)

```json
{
  "content": "...",
  "quotedFileContent": {"mimeType": "text/html", "value": "Hello World."}
}
```
**Result:** "Original content deleted". Google does not auto-locate the quoted text.

### Strategy 3: JSON anchor + `quotedFileContent`

```json
{
  "content": "...",
  "anchor": "{\"r\":\"head\",\"a\":[{\"txt\":{\"o\":1,\"l\":12}}]}",
  "quotedFileContent": {"mimeType": "text/html", "value": "Hello World."}
}
```
**Result:** "Original content deleted".

### Strategy 4: 0-based offset + `quotedFileContent`

Same as Strategy 3 but with `"o": 0` instead of `"o": 1`, in case the Drive API uses 0-based indexing.

**Result:** "Original content deleted".

### Strategy 5: Official documented line-based anchor

```json
{
  "content": "...",
  "anchor": "{\"region\":{\"kind\":\"drive#commentRegion\",\"line\":1,\"rev\":\"head\"}}",
  "quotedFileContent": {"mimeType": "text/html", "value": "Hello World."}
}
```
This is the only anchor format in Google's official documentation. It is designed for plain text files.

**Result:** "Original content deleted".

### Strategy 6: Reuse the `kix` anchor from a UI-created comment

```json
{
  "content": "...",
  "anchor": "kix.layzbrc0c7lb"
}
```
We copied the exact `anchor` string from the working UI-created comment.

**Result:** "Original content deleted".

### Strategy 7: Reuse `kix` anchor + `quotedFileContent`

```json
{
  "content": "...",
  "anchor": "kix.layzbrc0c7lb",
  "quotedFileContent": {"mimeType": "text/html", "value": "Hello World."}
}
```
Structurally identical to the UI-created comment when read back from the API.

**Result:** "Original content deleted".

## Analysis

### Where `kix` anchors live

The `kix.layzbrc0c7lb` anchor from the UI comment does **not** appear anywhere in the Docs API document JSON. The only `kix.*` identifiers in the document are for headers, footers, and list definitions — not for comment text ranges.

This means `kix` comment anchors are generated and stored in an internal layer of the Google Docs editor that is not exposed through any public API.

### Why the Drive API can't anchor comments

The Drive API treats the `anchor` field as an **opaque metadata string**. It stores whatever you pass in and returns it when you read the comment back. But it does not register the anchor with the Google Docs document engine.

When the Google Docs UI creates a comment, it performs two operations:
1. Creates the comment via the Drive API (with the `kix` anchor string)
2. Registers the anchor binding in an internal document layer (not accessible via API)

Step 2 is what makes the comment appear anchored to the highlighted text. The Drive API only handles step 1.

### Comparison: UI vs API comment (identical fields)

| Field | UI comment | API comment |
|---|---|---|
| `anchor` | `kix.layzbrc0c7lb` | `kix.layzbrc0c7lb` |
| `quotedFileContent` | `{"mimeType":"text/html","value":"Hello World."}` | `{"mimeType":"text/html","value":"Hello World."}` |
| `content` | `Hello World Comment` | `Test: kix anchor + quotedFileContent` |
| **Displayed correctly?** | **Yes** | **No — "Original content deleted"** |

The responses are structurally identical, yet only the UI-created comment works.

## Google Issue Tracker References

- [#357985444](https://issuetracker.google.com/issues/357985444) — "Anchored comments with Drive API not working for Google Docs" (open)
- [#36763384](https://issuetracker.google.com/issues/36763384) — "Provide ability to create a Drive API Comment anchor for Google Docs" (feature request, open since 2016)
- [#292610078](https://issuetracker.google.com/issues/292610078) — Similar issue for Google Sheets

## Impact on ExtraSuite

- **Pull (reading):** Works correctly. UI-created comments are read via `quotedFileContent` text search; API-created comments are read via JSON anchor offset parsing. Both produce correct `<comment-ref>` tags in `document.xml`.
- **Push (creating):** Comments are created and appear in the sidebar, but show "Original content deleted" instead of highlighting the referenced text. The comment content and position metadata are preserved, but the visual anchoring is broken.

## Current Behavior

ExtraSuite creates comments with both `anchor` (JSON offset/length format) and `quotedFileContent`. The comment is created successfully and appears in the document's comment sidebar, but without visual text anchoring.
