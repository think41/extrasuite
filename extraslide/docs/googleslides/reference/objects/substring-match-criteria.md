# SubstringMatchCriteria

A criteria that matches a specific string of text in a shape or table.

## Schema

```json
{
  "text": string,
  "matchCase": boolean,
  "searchByRegex": boolean
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `text` | string | The text to search for in the shape or table. |
| `matchCase` | boolean | Indicates whether the search should respect case: - `True`: the search is case sensitive. - `Fals... |
| `searchByRegex` | boolean | Optional. True if the find value should be treated as a regular expression. Any backslashes in th... |

