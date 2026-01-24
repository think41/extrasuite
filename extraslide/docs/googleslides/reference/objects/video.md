# Video

A PageElement kind representing a video.

## Schema

```json
{
  "url": string,
  "source": string,
  "id": string,
  "videoProperties": [VideoProperties]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `url` | string | An URL to a video. The URL is valid as long as the source video exists and sharing settings do no... |
| `source` | string | The video source. |
| `id` | string | The video source's unique identifier for this video. |
| `videoProperties` | [VideoProperties] | The properties of the video. |

### source Values

| Value | Description |
|-------|-------------|
| `SOURCE_UNSPECIFIED` | The video source is unspecified. |
| `YOUTUBE` | The video source is YouTube. |
| `DRIVE` | The video source is Google Drive. |

## Related Objects

- [VideoProperties](./video-properties.md)

