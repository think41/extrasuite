Google Forms - create and edit surveys and quizzes via a single JSON file.

## Workflow

  extrasuite form pull <url> [output_dir]   Download form
  # Edit form.json in <output_dir>/<form_id>/
  extrasuite form push <folder>             Apply changes to Google Forms
  extrasuite form create <title>            Create a new form

After push, form.json is updated with API-assigned IDs — no need to re-pull.

See `extrasuite form pull --help` for form.json structure, question types, and editing rules (self-contained).

## Commands

  extrasuite form pull --help       Pull flags, form.json layout, and editing rules
  extrasuite form push --help       Push flags
  extrasuite form diff --help       Offline debugging tool (no auth needed)
  extrasuite form create --help     Create a new form
  extrasuite form share --help      Share with trusted contacts

## Reference Docs (detailed)

  extrasuite form help                       List available reference topics
  extrasuite form help question-types        All question types, quiz mode, email collection
  extrasuite form help branching             Conditional section branching (goToSectionId)
