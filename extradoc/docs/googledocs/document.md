# Document

This guide covers key concepts for the Google Docs API, including primary methods, document access, and the workflow for creating documents.

## API Methods

The `documents` resource provides three main methods:

- **`documents.create`** — Creates a new document
- **`documents.get`** — Retrieves document contents
- **`documents.batchUpdate`** — Atomically performs multiple updates on a document

The `documents.get` and `documents.batchUpdate` methods require a `documentId` parameter, while `documents.create` returns the created document with its ID.

See @requests-and-responses.md for detailed information on these methods.

## Document ID

The `documentId` uniquely identifies a document and can be extracted from its URL:

```
https://docs.google.com/document/d/DOCUMENT_ID/edit
```

To extract it programmatically, use this regex pattern:

```
/document/d/([a-zA-Z0-9-_]+)
```

Document IDs remain stable even if the document name changes. They correspond to the `id` field in the Google Drive API's `files` resource.

## Managing Documents in Google Drive

Docs files are stored in Google Drive. While the Docs API offers standalone methods, integrating Google Drive API methods is often necessary. For example, use Drive's `files.copy` method to duplicate documents.

By default, new documents save to the user's root Drive folder. Documents have the MIME type `application/vnd.google-apps.document`.

### Working with Docs Files

Use Drive's `files.list` method to find document IDs. To filter for Docs files specifically, append:

```
q: mimeType = 'application/vnd.google-apps.document'
```

## Document Creation Workflow

The creation process involves:

1. Call `documents.create` to initialize a document
2. Receive HTTP response with the created document resource
3. Optionally call `documents.batchUpdate` to populate content
4. Receive response indicating success or providing update details

See @documents.md for code examples.

## Document Update Workflow

Updating requires understanding the document's current state first:

1. Call `documents.get` with the target `documentId`
2. Receive HTTP response with complete document structure
3. Parse the JSON response to identify changes needed
4. Call `documents.batchUpdate` to apply edits atomically
5. Receive confirmation of applied updates

This workflow assumes single-user edits; collaborative scenarios require additional considerations. See @best-practices.md for handling collaboration.
