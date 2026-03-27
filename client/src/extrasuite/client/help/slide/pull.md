Download a Google Slides presentation to a local folder.

## Usage

  extrasuite slides pull <url> [output_dir]

## Arguments

  url           Presentation URL or ID
  output_dir    Output directory (optional)

## Flags

  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

If output_dir is given, files are created directly in output_dir.
Otherwise, creates <presentation_id>/ in the current directory.

The folder contains:

  presentation.json   Presentation title, slide list, canvas dimensions
  styles.json         Theme colors and named font styles
  id_mapping.json     Maps internal object IDs to human-readable names
  slides/
    01/content.sml    Slide 1 content in SML (Slide Markup Language)
    02/content.sml    Slide 2 content
    ...
  .pristine/          Snapshot for diff/push comparison - do not edit
  .raw/               Raw API responses for debugging - do not edit

## What to Edit

Edit the slides/<nn>/content.sml files. Each file is a complete XML
representation of one slide's content.

Start by reading presentation.json to understand the slide structure,
then open the specific slide's content.sml to make changes.

For SML syntax, see: extrasuite slides help sml-reference

## Key Rules

  All text must be wrapped in <P> and <T> elements — never bare text
  Never use \n inside text — create new <P> elements instead
  Never modify id or range attributes — they are internal references
  Use hex colors (#rrggbb) — named colors are not supported
  Always re-pull before making further changes after a push

## Example

  extrasuite slides pull https://docs.google.com/presentation/d/abc123
  extrasuite slides pull https://docs.google.com/presentation/d/abc123 /tmp/slides
