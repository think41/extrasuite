# Range

Specifies a contiguous range of text.

**Type:** object

## Properties

- **segmentId** (string): The ID of the header, footer, or footnote that this range is contained in. An empty segment ID signifies the document's body.
- **startIndex** (integer): The zero-based start index of this range, in UTF-16 code units. In all current uses, a start index must be provided. This field is an Int32Value in order to accommodate future use cases with open-ended ranges.
- **endIndex** (integer): The zero-based end index of this range, exclusive, in UTF-16 code units. In all current uses, an end index must be provided. This field is an Int32Value in order to accommodate future use cases with open-ended ranges.
- **tabId** (string): The tab that contains this range. When omitted, the request applies to the first tab. In a document containing a single tab: - If provided, must match the singular tab's ID. - If omitted, the request applies to the singular tab. In a document containing multiple tabs: - If provided, the request applies to the specified tab. - If omitted, the request applies to the first tab in the document.
