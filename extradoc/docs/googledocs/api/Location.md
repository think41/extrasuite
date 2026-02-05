# Location

A particular location in the document.

**Type:** object

## Properties

- **segmentId** (string): The ID of the header, footer or footnote the location is in. An empty segment ID signifies the document's body.
- **index** (integer): The zero-based index, in UTF-16 code units. The index is relative to the beginning of the segment specified by segment_id.
- **tabId** (string): The tab that the location is in. When omitted, the request is applied to the first tab. In a document containing a single tab: - If provided, must match the singular tab's ID. - If omitted, the request applies to the singular tab. In a document containing multiple tabs: - If provided, the request applies to the specified tab. - If omitted, the request applies to the first tab in the document.
