Create a new Google Slides presentation, share it with your service account, and pull it locally.

## Usage

  extrasuite slides create <title> [output_dir]

## Arguments

  title       Title for the new presentation
  output_dir  Directory to pull the file into after creation (optional).
              If omitted, creates <presentation_id>/ in the current directory.

## Output

Prints the presentation URL and the service account email it was shared with.
Then automatically pulls the presentation into output_dir (or <presentation_id>/).
