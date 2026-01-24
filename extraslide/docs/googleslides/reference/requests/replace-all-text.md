# ReplaceAllTextRequest

Replaces all instances of text matching a criteria with replace text.

## Schema

```json
{
  "replaceAllText": {
    "replaceText": string,
    "pageObjectIds": array of string,
    "containsText": [SubstringMatchCriteria]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `replaceText` | string | No | The text that will replace the matched text. |
| `pageObjectIds` | array of string | No | If non-empty, limits the matches to page elements only on the given pages. Returns a 400 bad requ... |
| `containsText` | [SubstringMatchCriteria] | No | Finds text in a shape matching this substring. |

## Example

```json
{
  "requests": [
    {
      "replaceAllText": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [SubstringMatchCriteria](../objects/substring-match-criteria.md)

