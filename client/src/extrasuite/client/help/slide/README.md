Google Slides - edit presentations via SML (Slide Markup Language) files.

## Workflow

  extrasuite slides pull <url> [output_dir]   Download presentation
  # Edit slides/<nn>/content.sml files
  extrasuite slides push <folder>             Apply changes to Google Slides
  extrasuite slides create <title>            Create a new presentation

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

  extrasuite slides pull --help     Pull flags, folder layout, and key rules
  extrasuite slides push --help     Push flags
  extrasuite slides diff --help     Offline debugging tool (no auth needed)
  extrasuite slides create --help   Create a new presentation
  extrasuite slides share --help    Share with trusted contacts

## Reference Docs (detailed)

  extrasuite slides help                  List available reference topics
  extrasuite slides help sml-reference    SML elements, classes, and editing patterns
