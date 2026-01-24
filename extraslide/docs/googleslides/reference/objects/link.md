# Link

A hypertext link.

## Schema

```json
{
  "url": string,
  "relativeLink": string,
  "pageObjectId": string,
  "slideIndex": integer
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `url` | string | If set, indicates this is a link to the external web page at this URL. |
| `relativeLink` | string | If set, indicates this is a link to a slide in this presentation, addressed by its position. |
| `pageObjectId` | string | If set, indicates this is a link to the specific page in this presentation with this ID. A page w... |
| `slideIndex` | integer | If set, indicates this is a link to the slide at this zero-based index in the presentation. There... |

### relativeLink Values

| Value | Description |
|-------|-------------|
| `RELATIVE_SLIDE_LINK_UNSPECIFIED` | An unspecified relative slide link. |
| `NEXT_SLIDE` | A link to the next slide. |
| `PREVIOUS_SLIDE` | A link to the previous slide. |
| `FIRST_SLIDE` | A link to the first slide in the presentation. |
| `LAST_SLIDE` | A link to the last slide in the presentation. |

