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

## Example

  extrasuite forms pull https://docs.google.com/forms/d/abc123
  extrasuite forms pull https://docs.google.com/forms/d/abc123 --responses
