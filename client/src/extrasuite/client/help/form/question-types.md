# Form Question Types Reference

All question types and their JSON structures for form.json.

## Short Answer

```json
{
  "title": "What is your name?",
  "questionItem": {
    "question": {
      "required": true,
      "textQuestion": {"paragraph": false}
    }
  }
}
```

Set paragraph: true for long answer (multi-line text area).

## Multiple Choice (Single Answer)

```json
{
  "title": "What is the capital of France?",
  "questionItem": {
    "question": {
      "required": true,
      "choiceQuestion": {
        "type": "RADIO",
        "options": [
          {"value": "London"},
          {"value": "Paris"},
          {"value": "Berlin"},
          {"isOther": true}
        ]
      }
    }
  }
}
```

Note: isOther options must NOT have a value field (API returns 400 if you set one).

## Checkboxes (Multiple Answers)

Same as above but type: "CHECKBOX". Supports shuffle: true to randomize option order.

## Dropdown

Same as above but type: "DROP_DOWN".

## Linear Scale

```json
{
  "title": "How satisfied are you?",
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

## Date

```json
{
  "title": "Select a date:",
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

## Time

```json
{
  "title": "What time?",
  "questionItem": {
    "question": {
      "timeQuestion": {
        "duration": false
      }
    }
  }
}
```

duration: false = time of day (9:30 AM). duration: true = elapsed time (2h 30m).

## Rating

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

iconType: STAR, HEART, THUMB_UP

## Section (Page Break)

```json
{
  "title": "Section 2: Background",
  "description": "Tell us about your experience.",
  "pageBreakItem": {}
}
```

## Static Text

```json
{
  "title": "Important Notice",
  "description": "Please read carefully before proceeding.",
  "textItem": {}
}
```

## Image

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

## Video

```json
{
  "title": "Introduction",
  "videoItem": {
    "video": {"youtubeUri": "https://youtube.com/watch?v=..."},
    "caption": "Watch before starting"
  }
}
```

Only YouTube URLs are supported.

---

## Quiz Mode (Grading)

Enable quiz mode in settings, then add grading to each question:

```json
{
  "settings": {"quizSettings": {"isQuiz": true}}
}
```

Add grading to a question:
```json
{
  "question": {
    "required": true,
    "choiceQuestion": {"type": "RADIO", "options": [{"value": "3"}, {"value": "4"}]},
    "grading": {
      "pointValue": 1,
      "correctAnswers": {"answers": [{"value": "4"}]}
    }
  }
}
```

For checkbox questions, list all correct answers in the answers array.

---

## Email Collection

```json
{
  "settings": {
    "emailCollectionType": "VERIFIED"
  }
}
```

Values: DO_NOT_COLLECT, VERIFIED (auto-collects Google account email),
RESPONDER_INPUT (asks responder to type their email)

---

## Key Gotchas

  isOther option with value     Do NOT set value on isOther options (API returns 400)
  Newlines in title             Not allowed - use description for multi-line content
  Adding questions              Omit itemId and questionId (API assigns them)
  File upload questions         Read-only - cannot create via API
  Branching/logic               Not supported by the Google Forms API
