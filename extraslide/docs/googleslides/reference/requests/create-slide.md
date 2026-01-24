# CreateSlideRequest

Creates a slide.

## Schema

```json
{
  "createSlide": {
    "objectId": string,
    "insertionIndex": integer,
    "slideLayoutReference": [LayoutReference],
    "placeholderIdMappings": array of [LayoutPlaceholderIdMapping]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | A user-supplied object ID. If you specify an ID, it must be unique among all pages and page eleme... |
| `insertionIndex` | integer | No | The optional zero-based index indicating where to insert the slides. If you don't specify an inde... |
| `slideLayoutReference` | [LayoutReference] | No | Layout reference of the slide to be inserted, based on the *current master*, which is one of the ... |
| `placeholderIdMappings` | array of [LayoutPlaceholderIdMapping] | No | An optional list of object ID mappings from the placeholder(s) on the layout to the placeholders ... |

## Example

```json
{
  "requests": [
    {
      "createSlide": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [LayoutPlaceholderIdMapping](../objects/layout-placeholder-id-mapping.md)
- [LayoutReference](../objects/layout-reference.md)

