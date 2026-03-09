Google Slides - edit presentations via SML (Slide Markup Language) files.

## Workflow

  extrasuite slide pull <url> [output_dir]   Download presentation
  # Edit slides/<nn>/content.sml files
  extrasuite slide push <folder>             Apply changes to Google Slides
  extrasuite slide create <title>            Create a new presentation

See `extrasuite slide pull --help` for directory layout, SML key rules, and examples (self-contained).

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
Tailwind-inspired classes for styling. See `extrasuite slide help sml-reference` for the full reference.

## Commands

  extrasuite slide pull --help     Pull flags, folder layout, and key rules
  extrasuite slide push --help     Push flags
  extrasuite slide diff --help     Offline debugging tool (no auth needed)
  extrasuite slide create --help   Create a new presentation
  extrasuite slide share --help    Share with trusted contacts

## Reference Docs (detailed)

  extrasuite slide help                  List available reference topics
  extrasuite slide help sml-reference    SML elements, classes, and editing patterns
