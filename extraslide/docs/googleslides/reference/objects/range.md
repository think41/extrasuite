# Range

Specifies a contiguous range of an indexed collection, such as characters in text.

## Schema

```json
{
  "startIndex": integer,
  "endIndex": integer,
  "type": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `startIndex` | integer | The optional zero-based index of the beginning of the collection. Required for `FIXED_RANGE` and ... |
| `endIndex` | integer | The optional zero-based index of the end of the collection. Required for `FIXED_RANGE` ranges. |
| `type` | string | The type of range. |

### type Values

| Value | Description |
|-------|-------------|
| `RANGE_TYPE_UNSPECIFIED` | Unspecified range type. This value must not be used. |
| `FIXED_RANGE` | A fixed range. Both the `start_index` and `end_index` must be specified. |
| `FROM_START_INDEX` | Starts the range at `start_index` and continues until the end of the collection. The `end_index` ... |
| `ALL` | Sets the range to be the whole length of the collection. Both the `start_index` and the `end_inde... |

