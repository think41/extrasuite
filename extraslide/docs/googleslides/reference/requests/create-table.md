# CreateTableRequest

Creates a new table.

## Schema

```json
{
  "createTable": {
    "objectId": string,
    "elementProperties": [PageElementProperties],
    "rows": integer,
    "columns": integer
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | A user-supplied object ID. If you specify an ID, it must be unique among all pages and page eleme... |
| `elementProperties` | [PageElementProperties] | No | The element properties for the table. The table will be created at the provided size, subject to ... |
| `rows` | integer | No | Number of rows in the table. |
| `columns` | integer | No | Number of columns in the table. |

## Example

```json
{
  "requests": [
    {
      "createTable": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [PageElementProperties](../objects/page-element-properties.md)

