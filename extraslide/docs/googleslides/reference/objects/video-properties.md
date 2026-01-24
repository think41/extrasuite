# VideoProperties

The properties of the Video.

## Schema

```json
{
  "outline": [Outline],
  "autoPlay": boolean,
  "start": integer,
  "end": integer,
  "mute": boolean
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `outline` | [Outline] | The outline of the video. The default outline matches the defaults for new videos created in the ... |
| `autoPlay` | boolean | Whether to enable video autoplay when the page is displayed in present mode. Defaults to false. |
| `start` | integer | The time at which to start playback, measured in seconds from the beginning of the video. If set,... |
| `end` | integer | The time at which to end playback, measured in seconds from the beginning of the video. If set, t... |
| `mute` | boolean | Whether to mute the audio during video playback. Defaults to false. |

## Related Objects

- [Outline](./outline.md)

