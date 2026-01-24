# TextElement

A TextElement describes the content of a range of indices in the text content of a Shape or TableCell.

## Schema

```json
{
  "startIndex": integer,
  "endIndex": integer,
  "paragraphMarker": [ParagraphMarker],
  "textRun": [TextRun],
  "autoText": [AutoText]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `startIndex` | integer | The zero-based start index of this text element, in Unicode code units. |
| `endIndex` | integer | The zero-based end index of this text element, exclusive, in Unicode code units. |
| `paragraphMarker` | [ParagraphMarker] | A marker representing the beginning of a new paragraph. The `start_index` and `end_index` of this... |
| `textRun` | [TextRun] | A TextElement representing a run of text where all of the characters in the run have the same Tex... |
| `autoText` | [AutoText] | A TextElement representing a spot in the text that is dynamically replaced with content that can ... |

## Related Objects

- [AutoText](./auto-text.md)
- [ParagraphMarker](./paragraph-marker.md)
- [TextRun](./text-run.md)

