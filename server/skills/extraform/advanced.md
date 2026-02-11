# ExtraForm Advanced Guide

Less common question types, media items, and form settings.

---

## Scale Question (Linear Scale)

```json
{
  "title": "How satisfied are you with our service?",
  "questionItem": {
    "question": {
      "scaleQuestion": {
        "low": 1,
        "high": 5,
        "lowLabel": "Very dissatisfied",
        "highLabel": "Very satisfied"
      }
    }
  }
}
```

- `low` and `high` define the numeric range
- `lowLabel` and `highLabel` are optional endpoint labels

## Rating Question

```json
{
  "title": "Rate this product:",
  "questionItem": {
    "question": {
      "ratingQuestion": {
        "iconType": "STAR",
        "ratingScaleLevel": 5
      }
    }
  }
}
```

Icon types: `STAR`, `HEART`, `THUMB_UP`

## Date Question

```json
{
  "title": "When is your birthday?",
  "questionItem": {
    "question": {
      "dateQuestion": {
        "includeYear": true,
        "includeTime": false
      }
    }
  }
}
```

## Time Question

```json
{
  "title": "What time do you usually wake up?",
  "questionItem": {
    "question": {
      "timeQuestion": {
        "duration": false
      }
    }
  }
}
```

- `duration: false` — time of day (e.g., 9:30 AM)
- `duration: true` — elapsed time (e.g., 2 hours 30 minutes)

---

## "Other" Option

Add an "Other" free-text option to choice questions:

```json
"options": [
  { "value": "Option A" },
  { "value": "Option B" },
  { "isOther": true }
]
```

**Important:** Do NOT set `value` on an `isOther` option — the API returns 400.

## Shuffle Options

Randomize option order for responders:

```json
"choiceQuestion": {
  "type": "RADIO",
  "shuffle": true,
  "options": [...]
}
```

---

## Image Item

```json
{
  "title": "Company Logo",
  "imageItem": {
    "image": {
      "sourceUri": "https://example.com/logo.png",
      "altText": "Company logo"
    }
  }
}
```

## Video Item

```json
{
  "title": "Introduction Video",
  "videoItem": {
    "video": {
      "youtubeUri": "https://youtube.com/watch?v=dQw4w9WgXcQ"
    },
    "caption": "Watch this before starting the form"
  }
}
```

Only YouTube URLs are supported.

## Static Text Item

Display instructions or information without a question:

```json
{
  "title": "Important Notice",
  "description": "Please complete all sections before submitting.\nYou can save and return later.",
  "textItem": {}
}
```

---

## Email Collection Settings

```json
{
  "settings": {
    "emailCollectionType": "VERIFIED"
  }
}
```

| Value | Behavior |
|-------|----------|
| `DO_NOT_COLLECT` | No email collection |
| `VERIFIED` | Collects verified Google account email automatically |
| `RESPONDER_INPUT` | Asks responder to type their email |

---

## API Limitations

- **File upload questions** — cannot be created via API (read-only if already present)
- **documentTitle** — read-only, set via Google Drive
- **Response editing** — cannot modify submitted responses
- **Branching/logic** — not supported by the Google Forms API
