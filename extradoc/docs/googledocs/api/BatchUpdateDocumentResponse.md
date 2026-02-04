# BatchUpdateDocumentResponse

Response message from a BatchUpdateDocument request.

**Type:** object

## Properties

- **documentId** (string): The ID of the document to which the updates were applied to.
- **replies** (array of [Response](response.md)): The reply of the updates. This maps 1:1 with the updates, although replies to some requests may be empty.
- **writeControl** ([WriteControl](writecontrol.md)): The updated write control after applying the request.
