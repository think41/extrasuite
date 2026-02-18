Google Slides - edit presentations via SML (Slide Markup Language) files.

## Workflow

  extrasuite slide pull <url> [output_dir]   Download presentation
  # Edit slides/<nn>/content.sml files
  extrasuite slide push <folder>             Apply changes to Google Slides
  extrasuite slide create <title>            Create a new presentation

After push, always re-pull before making more changes.

## Directory Structure

  <presentation_id>/
    presentation.json       START HERE - title, slide list, dimensions
    styles.json             Theme colors and font styles
    id_mapping.json         Object ID to name mapping
    slides/
      01/content.sml        Slide content in SML format
      02/content.sml
      ...
    .pristine/              Internal state - do not edit

## SML Format

SML is an HTML-inspired markup language. Each slide is an XML file with
positioned elements (TextBox, Rect, Ellipse, Image, etc.) using
Tailwind-inspired classes for styling.

Key rules:
  All text must be wrapped in <P> and <T> elements (never bare text)
  Never use \n in text - create new <P> elements instead
  Never modify id or range attributes - they are internal references
  Use hex colors - named colors are not supported

## Example

  <TextBox id="title" class="x-72 y-144 w-576 h-80 font-family-roboto text-size-36">
    <P><T>Slide Title</T></P>
  </TextBox>

  <Rect class="x-100 y-300 w-200 h-100 fill-#4285f4"/>

## Commands

  extrasuite slide pull --help     Pull flags and folder layout
  extrasuite slide push --help     Push flags
  extrasuite slide diff --help     Offline debugging tool (no auth needed)
  extrasuite slide create --help   Create a new presentation

## Reference Docs (detailed)

  extrasuite slide help                  List available reference topics
  extrasuite slide help sml-reference    SML elements, classes, and editing patterns
