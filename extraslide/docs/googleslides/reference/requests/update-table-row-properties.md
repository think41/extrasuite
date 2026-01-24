# UpdateTableRowPropertiesRequest

Updates the properties of a Table row.

## Schema

```json
{
  "updateTableRowProperties": {
    "objectId": string,
    "rowIndices": array of integer,
    "tableRowProperties": [TableRowProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the table. |
| `rowIndices` | array of integer | No | The list of zero-based indices specifying which rows to update. If no indices are provided, all r... |
| `tableRowProperties` | [TableRowProperties] | No | The table row properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `tableRowProper... |

## Example

```json
{
  "requests": [
    {
      "updateTableRowProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableRowProperties](../objects/table-row-properties.md)

