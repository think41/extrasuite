Google Forms - create and edit surveys and quizzes via a single JSON file.

## Workflow

  extrasuite form pull <url> [output_dir]   Download form
  # Edit form.json in <output_dir>/<form_id>/
  extrasuite form push <folder>             Apply changes to Google Forms
  extrasuite form create <title>            Create a new form

After push, always re-pull before making more changes.

## Directory Structure

  <form_id>/
    form.json     The only file you edit - questions, sections, settings
    .pristine/    Internal state - do not edit
    .raw/         Raw API responses - do not edit

## form.json Structure

```json
{
  "formId": "abc123",
  "info": {
    "title": "Form title shown to responders",
    "description": "Optional description"
  },
  "settings": {
    "quizSettings": {"isQuiz": false}
  },
  "items": [...]
}
```

Editable: info.title, info.description, settings, items
Read-only: formId, revisionId, info.documentTitle, responderUri

## Question Types (in items array)

  textQuestion          Short answer (paragraph: false) or long answer (paragraph: true)
  choiceQuestion        Multiple choice (RADIO), checkboxes (CHECKBOX), dropdown (DROP_DOWN)
  scaleQuestion         Linear scale with labels
  dateQuestion          Date picker
  timeQuestion          Time picker
  ratingQuestion        Star/heart/thumb rating
  pageBreakItem         Section divider
  textItem              Static text (no answer)
  imageItem             Image display
  videoItem             YouTube video

## Adding Questions

Omit itemId and questionId - the API assigns them:
  {"title": "Question text", "questionItem": {"question": {<type>}}}

## Editing Questions

Modify in place, keeping itemId and questionId intact.

## Reordering

Change the order in the items array. The diff engine handles move operations.

## Deleting

Remove the item from the items array.

## Commands

  extrasuite form pull --help       Pull flags (including --responses)
  extrasuite form push --help       Push flags
  extrasuite form diff --help       Offline debugging tool (no auth needed)
  extrasuite form create --help     Create a new form

## Reference Docs (detailed)

  extrasuite form help                       List available reference topics
  extrasuite form help question-types        All question types, quiz mode, email collection
