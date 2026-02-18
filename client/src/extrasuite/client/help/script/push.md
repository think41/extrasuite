Apply local changes to a Google Apps Script project.

## Usage

  extrasuite script push <folder>

## Arguments

  folder    Path to the script project folder (created by pull)

## Flags

  --skip-lint   Skip JavaScript linting before push

## How It Works

Runs lint on all .js files, then uploads all files to the Apps Script API,
replacing the entire project content in a single operation.

## After Push

Always re-pull before making more changes.

## Notes

- Push replaces all project files (added, modified, and deleted files are all handled)
- Lint errors block the push; fix them or use --skip-lint to bypass
- Lint warnings are shown but do not block the push
