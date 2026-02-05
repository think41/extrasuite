# DeletePositionedObjectRequest

Deletes a PositionedObject from the document.

**Type:** object

## Properties

- **objectId** (string): The ID of the positioned object to delete.
- **tabId** (string): The tab that the positioned object to delete is in. When omitted, the request is applied to the first tab. In a document containing a single tab: - If provided, must match the singular tab's ID. - If omitted, the request applies to the singular tab. In a document containing multiple tabs: - If provided, the request applies to the specified tab. - If omitted, the request applies to the first tab in the document.
