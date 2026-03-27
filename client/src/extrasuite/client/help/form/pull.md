Download a Google Form to a local folder.

## Usage

  extrasuite forms pull <url> [output_dir]

## Arguments

  url           Form URL or ID
  output_dir    Output directory (optional)

## Flags

  --responses         Include form responses in the output
  --max-responses N   Max responses to fetch (default: 100)
  --no-raw            Skip saving raw API responses (.raw/ folder)

## Output

If output_dir is given, files are created directly in output_dir.
Otherwise, creates <form_id>/ in the current directory.

The folder contains:

  form.json     Complete form definition: title, settings, all questions
  .pristine/    Snapshot for diff/push comparison - do not edit
  .raw/         Raw API responses for debugging - do not edit

When --responses is used, responses are included in the pull output.

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

## Editing form.json

  Add question    Add an object to items (omit itemId/questionId — API assigns them)
  Edit question   Modify in place, keeping itemId and questionId intact
  Reorder         Change the order in the items array — diff engine handles moves
  Delete          Remove the item from the items array

## Question Types (items array)

  textQuestion    Short answer (paragraph: false) or long answer (paragraph: true)
  choiceQuestion  Multiple choice (RADIO), checkboxes (CHECKBOX), dropdown (DROP_DOWN)
  scaleQuestion   Linear scale with labels
  dateQuestion    Date picker
  timeQuestion    Time picker
  ratingQuestion  Star/heart/thumb rating
  pageBreakItem   Section divider
  textItem        Static text (no answer)
  imageItem       Image display
  videoItem       YouTube video

## Notes

After push, form.json is updated with API-assigned IDs — no need to re-pull.

## Example

  extrasuite forms pull https://docs.google.com/forms/d/abc123
  extrasuite forms pull https://docs.google.com/forms/d/abc123 --responses
