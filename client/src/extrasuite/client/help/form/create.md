Create a new Google Form, share it with your service account, and pull it locally.

## Usage

  extrasuite forms create <title> [output_dir]

## Arguments

  title       Title for the new form
  output_dir  Directory to pull the file into after creation (optional).
              If omitted, creates <form_id>/ in the current directory.

## Output

Prints the form URL and the service account email it was shared with.
Then automatically pulls the form into output_dir (or <form_id>/).
