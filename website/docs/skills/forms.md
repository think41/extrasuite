# Google Forms Skill

Create and edit Google Forms using the declarative pull-edit-diff-push workflow.

!!! success "Status: Stable"
    This skill is fully supported for production use.

## Overview

The Google Forms skill enables your AI agent to:

- Pull forms into editable JSON
- Add, modify, and remove questions
- Change question types and options
- Update form structure and sections
- Preview changes before applying
- Push edits back to Google Forms

All editing is declarative - the agent edits a local `form.json` file, and ExtraSuite computes the minimal API calls to sync changes.

## The Workflow

```bash
# 1. Pull - download the form
extraform pull https://docs.google.com/forms/d/1FAIpQLSd.../edit

# 2. Edit - modify form.json locally

# 3. Diff - preview changes (dry run)
extraform diff 1FAIpQLSd.../

# 4. Push - apply changes
extraform push 1FAIpQLSd.../
```

## On-Disk Format

After `pull`, you'll have:

```
<form_id>/
  form.json                 # Form structure - edit this!
  responses.tsv             # Read-only snapshot of responses
  .raw/
    form.json               # Raw API response
    responses.json          # Raw responses (if fetched)
  .pristine/
    form.zip                # Original state for diff
```

## Editing form.json

The form structure is a cleaned-up version of the Google Forms API:

```json
{
  "formId": "1FAIpQLSd...",
  "info": {
    "title": "My Survey",
    "description": "Please fill out this survey"
  },
  "items": [
    {
      "itemId": "abc123",
      "title": "What is your name?",
      "questionItem": {
        "question": {
          "required": true,
          "textQuestion": {
            "paragraph": false
          }
        }
      }
    }
  ]
}
```

## Question Types

| Type | JSON Key | Example |
|------|----------|---------|
| Short answer | `textQuestion` | `{"paragraph": false}` |
| Long answer | `textQuestion` | `{"paragraph": true}` |
| Multiple choice | `choiceQuestion` | `{"type": "RADIO", "options": [...]}` |
| Checkboxes | `choiceQuestion` | `{"type": "CHECKBOX", "options": [...]}` |
| Dropdown | `choiceQuestion` | `{"type": "DROP_DOWN", "options": [...]}` |
| Linear scale | `scaleQuestion` | `{"low": 1, "high": 5}` |
| Date | `dateQuestion` | `{"includeYear": true}` |
| Time | `timeQuestion` | `{"duration": false}` |
| Rating | `ratingQuestion` | `{"iconType": "STAR", "ratingScaleLevel": 5}` |

## Non-Question Items

| Type | Purpose |
|------|---------|
| `pageBreakItem` | Section divider |
| `textItem` | Static text/instructions |
| `imageItem` | Embedded image |
| `videoItem` | Embedded YouTube video |

## Common Edits

### Add a question

Add a new object to the `items` array:

```json
{
  "title": "Rate your experience",
  "questionItem": {
    "question": {
      "required": true,
      "ratingQuestion": {
        "iconType": "STAR",
        "ratingScaleLevel": 5
      }
    }
  }
}
```

### Change a question type

Replace the question type key. For example, change a short answer to multiple choice:

```json
{
  "title": "What is your department?",
  "questionItem": {
    "question": {
      "required": true,
      "choiceQuestion": {
        "type": "RADIO",
        "options": [
          {"value": "Engineering"},
          {"value": "Sales"},
          {"value": "Marketing"}
        ]
      }
    }
  }
}
```

### Reorder questions

Reorder objects in the `items` array. The diff engine will compute the necessary move operations.

## CLI Options

```bash
# Pull with responses
extraform pull <url> --responses --max-responses 200

# Pull without raw API data
extraform pull <url> --no-raw

# Force push despite warnings
extraform push <folder> --force
```

## Limitations

- **File upload questions**: Cannot be created via API (read-only)
- **Responses**: Read-only, cannot modify submitted responses
- **documentTitle**: Read-only, update via Google Drive

---

**Related:**

- [Google Sheets Skill](sheets.md) - For spreadsheet operations
- [Google Docs Skill](docs.md) - For document operations
- [Google Slides Skill](slides.md) - For presentation operations
