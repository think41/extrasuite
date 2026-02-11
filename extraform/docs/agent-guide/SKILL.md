# ExtraForm Agent Guide

Create and edit Google Forms (questions, quizzes, sections) via local files using the pull-edit-diff-push workflow.

## Workflow

```bash
uv run python -m extraform pull <url> <root-folder>    # Download form to <root-folder>/<form_id>/
# ... edit form.json in <root-folder>/<form_id>/
uv run python -m extraform diff <root-folder>/<form_id>   # Preview changes (dry run)
uv run python -m extraform push <root-folder>/<form_id>   # Apply changes to Google Forms
```

**After push, always re-pull before making more changes** — the pristine state is not auto-updated.

## Directory Structure

```
<form_id>/
  form.json               # START HERE - the only file you edit
  .raw/                    # Raw API responses (internal use only)
  .pristine/               # Original state for diff comparison (internal use only)
```

## form.json Structure

```json
{
  "formId": "abc123...",
  "revisionId": "00000002",
  "info": {
    "title": "Form Title (shown to responders)",
    "documentTitle": "Drive document name (read-only)",
    "description": "Form description"
  },
  "settings": {
    "quizSettings": { "isQuiz": true },
    "emailCollectionType": "DO_NOT_COLLECT"
  },
  "items": [...]
}
```

**Editable fields:** `info.title`, `info.description`, `settings`, `items`
**Read-only fields:** `formId`, `revisionId`, `responderUri`, `info.documentTitle`, `publishSettings`

---

## Adding Questions

Add an item to the `items` array **without** `itemId` or `questionId` — the API assigns these.

**Multiple choice (single answer):**
```json
{
  "title": "What is the capital of France?",
  "questionItem": {
    "question": {
      "required": true,
      "choiceQuestion": {
        "type": "RADIO",
        "options": [
          { "value": "London" },
          { "value": "Paris" },
          { "value": "Berlin" },
          { "value": "Madrid" }
        ]
      }
    }
  }
}
```

**Checkboxes (multiple answers):**
```json
{
  "title": "Select all programming languages you know:",
  "questionItem": {
    "question": {
      "choiceQuestion": {
        "type": "CHECKBOX",
        "options": [
          { "value": "Python" },
          { "value": "JavaScript" },
          { "value": "Go" },
          { "value": "Other", "isOther": true }
        ]
      }
    }
  }
}
```

**Short answer / Long answer:**
```json
{
  "title": "What is your name?",
  "questionItem": {
    "question": {
      "required": true,
      "textQuestion": { "paragraph": false }
    }
  }
}
```
Set `"paragraph": true` for long answer (multi-line text area).

**Dropdown:**
Same as choice question but with `"type": "DROP_DOWN"`.

## Quiz Mode (Grading)

Enable quiz mode in settings, then add `grading` to each question:

```json
{
  "settings": {
    "quizSettings": { "isQuiz": true }
  }
}
```

```json
{
  "title": "What is 2 + 2?",
  "questionItem": {
    "question": {
      "required": true,
      "choiceQuestion": {
        "type": "RADIO",
        "options": [
          { "value": "3" },
          { "value": "4" },
          { "value": "5" }
        ]
      },
      "grading": {
        "pointValue": 1,
        "correctAnswers": {
          "answers": [
            { "value": "4" }
          ]
        }
      }
    }
  }
}
```

For checkbox questions, list all correct answers:
```json
"correctAnswers": {
  "answers": [
    { "value": "Option A" },
    { "value": "Option C" }
  ]
}
```

## Sections (Page Breaks)

```json
{
  "title": "Section 2: Background",
  "description": "Tell us about your experience.",
  "pageBreakItem": {}
}
```

## Editing Existing Questions

Modify the item in place — keep `itemId` and `questionId` intact. Change `title`, `description`, options, `required`, `grading`, etc.

## Deleting Questions

Remove the item from the `items` array.

## Reordering Questions

Change the order of items in the `items` array. The diff engine handles move operations automatically.

---

## Key Gotchas

| Issue | Solution |
|-------|----------|
| `isOther` option with value | Do NOT set `value` on options with `"isOther": true` — API returns 400 |
| Newlines in title | `title` field cannot contain newlines — use `description` for code snippets |
| Newlines in description | `description` field supports newlines — use for code blocks and multi-line content |
| New items have `itemId` | Remove `itemId` and `questionId` when adding new questions — API assigns them |
| Changes not applied after push | Re-pull before making more changes |

---

## Quick Reference

| Question Type | JSON Key | Key Fields |
|---------------|----------|------------|
| Short answer | `textQuestion` | `paragraph: false` |
| Long answer | `textQuestion` | `paragraph: true` |
| Multiple choice | `choiceQuestion` | `type: "RADIO"`, `options: [...]` |
| Checkboxes | `choiceQuestion` | `type: "CHECKBOX"`, `options: [...]` |
| Dropdown | `choiceQuestion` | `type: "DROP_DOWN"`, `options: [...]` |
| Linear scale | `scaleQuestion` | `low`, `high`, `lowLabel`, `highLabel` |
| Date | `dateQuestion` | `includeYear`, `includeTime` |
| Time | `timeQuestion` | `duration: false` (time of day) or `true` (elapsed) |
| Rating | `ratingQuestion` | `iconType: "STAR"/"HEART"/"THUMB_UP"`, `ratingScaleLevel` |
| Section | `pageBreakItem` | `{}` (empty object) |
| Static text | `textItem` | `{}` (empty object, use title/description for content) |

## Advanced Guides

- **[advanced.md](advanced.md)** — Scale questions, date/time questions, rating questions, images, videos, "Other" options, shuffle, email collection settings
