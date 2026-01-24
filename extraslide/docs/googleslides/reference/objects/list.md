# List

A List describes the look and feel of bullets belonging to paragraphs associated with a list. A paragraph that is part of a list has an implicit reference to that list's ID.

## Schema

```json
{
  "listId": string,
  "nestingLevel": map<string, [NestingLevel]>
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `listId` | string | The ID of the list. |
| `nestingLevel` | map<string, [NestingLevel]> | A map of nesting levels to the properties of bullets at the associated level. A list has at most ... |

