Google Forms - create and edit surveys and quizzes via a single JSON file.

## Workflow

  extrasuite forms pull <url> [output_dir]   Download form
  # Edit form.json in <output_dir>/
  extrasuite forms push <folder>             Apply changes to Google Forms
  extrasuite forms create <title>            Create a new form

After push, form.json is updated with API-assigned IDs — no need to re-pull.

See `extrasuite form pull --help` for form.json structure, question types, and editing rules (self-contained).

## Commands

  extrasuite forms pull --help       Pull flags, form.json layout, and editing rules
  extrasuite forms push --help       Push flags
  extrasuite forms diff --help       Offline debugging tool (no auth needed)
  extrasuite forms create --help     Create a new form
  extrasuite forms share --help      Share with trusted contacts

## Reference Docs (detailed)

  extrasuite forms help                       List available reference topics
  extrasuite forms help question-types        All question types, quiz mode, email collection
  extrasuite forms help branching             Conditional section branching (goToSectionId)
