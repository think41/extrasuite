Create a new Google Doc and initialize it from a folder of markdown files.

## Usage

  extrasuite doc create-md <title> [output_dir] [--from FOLDER]

## Arguments

  title         Title for the new document
  output_dir    Directory to save the local folder (default: current directory)

## Options

  --from FOLDER    Folder of .md files to import as tab content.
                   Files are assigned to tabs in alphabetical order.
                   The first file becomes the content of Tab 1; additional
                   files each create a new tab named after the file stem.

## Behavior

Without --from, creates an empty document and pulls it in markdown format
to the local folder (identical to `doc create` followed by `doc pull-md`).

With --from:
  1. Creates the document and shares it with the service account
  2. Pulls the empty document in markdown format
  3. Copies your .md files into the local folder
  4. Pushes the content to Google Docs
  5. Re-pulls to sync the pristine state

## Examples

  # Create an empty doc and pull it
  extrasuite doc create-md "My Document"

  # Create and populate from a folder of markdown files
  extrasuite doc create-md "Product Docs" --from ./my-docs/

  # Create in a specific output directory
  extrasuite doc create-md "My Document" /tmp/workspace --from ./my-docs/
