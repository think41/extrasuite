# On-Disk Format

This document describes the file format used by ExtraForm to represent Google Forms on disk.

## Directory Structure

```
<form_id>/
  form.json                 # Form metadata, settings, and questions
  responses.tsv             # Read-only snapshot of responses (optional)
  .raw/
    form.json               # Raw API response
    responses.json          # Raw responses API response (if fetched)
  .pristine/
    form.zip                # Original state for diff comparison
```

## form.json

The main editable file containing the form structure. Format closely mirrors the Google Forms API.

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `formId` | string | Unique form identifier (read-only) |
| `revisionId` | string | Revision ID for concurrency (read-only, valid 24h) |
| `responderUri` | string | Public URL for form submission (read-only) |
| `linkedSheetId` | string | Linked Google Sheet ID (read-only) |
| `info` | object | Form title and description |
| `settings` | object | Form settings (quiz, email collection) |
| `items` | array | List of form items (questions, sections, media) |

### Info Object

```json
{
  "info": {
    "title": "Survey Title",
    "documentTitle": "Document Name in Drive",
    "description": "Form description shown to responders"
  }
}
```

- `title`: Visible to responders, editable
- `documentTitle`: Read-only, shown in Google Drive
- `description`: Editable form description

### Settings Object

```json
{
  "settings": {
    "quizSettings": {
      "isQuiz": false
    },
    "emailCollectionType": "VERIFIED"
  }
}
```

Email collection types:
- `DO_NOT_COLLECT`: Don't collect emails
- `VERIFIED`: Collect verified Google account emails
- `RESPONDER_INPUT`: Allow manual email entry

### Items Array

Each item in the array represents a form element. Items are identified by `itemId` (assigned by the API).

#### Question Item

```json
{
  "itemId": "abc123",
  "title": "What is your name?",
  "description": "Optional help text",
  "questionItem": {
    "question": {
      "questionId": "def456",
      "required": true,
      "textQuestion": {
        "paragraph": false
      }
    }
  }
}
```

#### Question Types

**Text Question (Short/Long Answer)**
```json
"textQuestion": {
  "paragraph": false  // false=short, true=long
}
```

**Choice Question (Radio/Checkbox/Dropdown)**
```json
"choiceQuestion": {
  "type": "RADIO",  // or "CHECKBOX", "DROP_DOWN"
  "options": [
    { "value": "Option 1" },
    { "value": "Option 2" },
    { "value": "Other", "isOther": true }
  ],
  "shuffle": false
}
```

**Scale Question**
```json
"scaleQuestion": {
  "low": 1,
  "high": 5,
  "lowLabel": "Poor",
  "highLabel": "Excellent"
}
```

**Date Question**
```json
"dateQuestion": {
  "includeYear": true,
  "includeTime": false
}
```

**Time Question**
```json
"timeQuestion": {
  "duration": false  // false=time of day, true=elapsed time
}
```

**Rating Question**
```json
"ratingQuestion": {
  "iconType": "STAR",  // or "HEART", "THUMB_UP"
  "ratingScaleLevel": 5
}
```

**File Upload Question** (Read-only - cannot create via API)
```json
"fileUploadQuestion": {
  "folderId": "drive_folder_id",
  "types": ["IMAGE", "PDF"],
  "maxFiles": 5,
  "maxFileSize": "10485760"
}
```

#### Non-Question Items

**Page Break (Section)**
```json
{
  "itemId": "xyz789",
  "title": "Section Title",
  "description": "Section description",
  "pageBreakItem": {}
}
```

**Text Item (Static Text)**
```json
{
  "itemId": "txt123",
  "title": "Instructions",
  "description": "Please read carefully...",
  "textItem": {}
}
```

**Image Item**
```json
{
  "itemId": "img123",
  "imageItem": {
    "image": {
      "sourceUri": "https://example.com/image.png",
      "altText": "Description"
    }
  }
}
```

**Video Item**
```json
{
  "itemId": "vid123",
  "videoItem": {
    "video": {
      "youtubeUri": "https://youtube.com/watch?v=..."
    },
    "caption": "Video caption"
  }
}
```

## responses.tsv

Read-only tab-separated file containing form responses.

```tsv
responseId	timestamp	respondentEmail	Question1	Question2
resp_001	2024-01-15T10:30:00Z	alice@example.com	Answer 1	Answer 2
resp_002	2024-01-15T11:45:00Z	bob@example.com	Answer 1	Answer 2
```

Column headers are derived from question titles (sanitized for TSV compatibility).

## .raw Directory

Contains unmodified API responses for debugging and reference.

- `form.json`: Raw form structure from `GET /v1/forms/{formId}`
- `responses.json`: Raw responses from `GET /v1/forms/{formId}/responses`

## .pristine Directory

Contains `form.zip` with the original form state from the last pull or push. Used by the diff engine to detect changes.

**Do not modify files in .pristine/** - this will break the diff/push workflow.

## API Limitations

| Feature | Limitation |
|---------|------------|
| File upload questions | Cannot create via API (read-only) |
| documentTitle | Read-only, set via Drive API |
| questionId | Read-only, auto-assigned on creation |
| itemId | Read-only after creation |
| revisionId | Valid for 24 hours only |
| publishSettings | Read-only |
