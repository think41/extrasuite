Download a Google Form to a local folder.

## Usage

  extrasuite form pull <url> [output_dir]

## Arguments

  url           Form URL or ID
  output_dir    Output directory (default: current directory)

## Flags

  --responses         Include form responses in the output
  --max-responses N   Max responses to fetch (default: 100)
  --no-raw            Skip saving raw API responses (.raw/ folder)

## Output

Creates <output_dir>/<form_id>/ with:

  form.json     Complete form definition: title, settings, all questions
  .pristine/    Snapshot for diff/push comparison - do not edit
  .raw/         Raw API responses for debugging - do not edit

When --responses is used, responses are included in the pull output.

## Example

  extrasuite form pull https://docs.google.com/forms/d/abc123
  extrasuite form pull https://docs.google.com/forms/d/abc123 --responses
