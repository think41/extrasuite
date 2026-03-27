Create a new Google Doc, share it with your service account, and pull it locally.

## Usage

  extrasuite docs create <title> [output_dir]

## Arguments

  title       Title for the new document
  output_dir  Directory to pull the file into after creation (optional).
              If omitted, creates <document_id>/ in the current directory.

## Output

Prints the document URL and the service account email it was shared with.
Then automatically pulls the document into output_dir (or <document_id>/).
