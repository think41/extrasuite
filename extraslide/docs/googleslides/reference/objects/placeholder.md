# Placeholder

The placeholder information that uniquely identifies a placeholder shape.

## Schema

```json
{
  "type": string,
  "index": integer,
  "parentObjectId": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `type` | string | The type of the placeholder. |
| `index` | integer | The index of the placeholder. If the same placeholder types are present in the same page, they wo... |
| `parentObjectId` | string | The object ID of this shape's parent placeholder. If unset, the parent placeholder shape does not... |

### type Values

| Value | Description |
|-------|-------------|
| `NONE` | Default value, signifies it is not a placeholder. |
| `BODY` | Body text. |
| `CHART` | Chart or graph. |
| `CLIP_ART` | Clip art image. |
| `CENTERED_TITLE` | Title centered. |
| `DIAGRAM` | Diagram. |
| `DATE_AND_TIME` | Date and time. |
| `FOOTER` | Footer text. |
| `HEADER` | Header text. |
| `MEDIA` | Multimedia. |
| `OBJECT` | Any content type. |
| `PICTURE` | Picture. |
| `SLIDE_NUMBER` | Number of a slide. |
| `SUBTITLE` | Subtitle. |
| `TABLE` | Table. |
| `TITLE` | Slide title. |
| `SLIDE_IMAGE` | Slide image. |

