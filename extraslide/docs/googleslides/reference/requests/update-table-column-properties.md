# UpdateTableColumnPropertiesRequest

Updates the properties of a Table column.

## Schema

```json
{
  "updateTableColumnProperties": {
    "objectId": string,
    "columnIndices": array of integer,
    "tableColumnProperties": [TableColumnProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the table. |
| `columnIndices` | array of integer | No | The list of zero-based indices specifying which columns to update. If no indices are provided, al... |
| `tableColumnProperties` | [TableColumnProperties] | No | The table column properties to update. If the value of `table_column_properties#column_width` in ... |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `tableColumnPro... |

## Example

```json
{
  "requests": [
    {
      "updateTableColumnProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableColumnProperties](../objects/table-column-properties.md)

