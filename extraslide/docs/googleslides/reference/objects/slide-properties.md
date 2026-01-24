# SlideProperties

The properties of Page that are only relevant for pages with page_type SLIDE.

## Schema

```json
{
  "layoutObjectId": string,
  "masterObjectId": string,
  "notesPage": [Page],
  "isSkipped": boolean
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `layoutObjectId` | string | The object ID of the layout that this slide is based on. This property is read-only. |
| `masterObjectId` | string | The object ID of the master that this slide is based on. This property is read-only. |
| `notesPage` | [Page] | The notes page that this slide is associated with. It defines the visual appearance of a notes pa... |
| `isSkipped` | boolean | Whether the slide is skipped in the presentation mode. Defaults to false. |

## Related Objects

- [Page](./page.md)

