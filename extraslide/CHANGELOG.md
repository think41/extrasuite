# Changelog

All notable changes to the extraslide library will be documented in this file.

## [0.2.0] - 2026-02-11

### Breaking Changes

- Removed CLI entry point (`python -m extraslide`). Use `extrasuite slide pull/diff/push` instead.
- Removed dependency on `extrasuite` (client) package.

## [0.1.0] - 2026-02-11

### Added

- Initial release (alpha)
- **Pull**: Download Google Slides to a local folder with SML (Slide Markup Language) format
  - Per-slide `content.sml` files in minimal XML
  - `styles.json` - Style definitions (position, fill, stroke, text) per element
  - `id_mapping.json` - Clean ID to Google object ID mapping
  - `presentation.json` - Metadata (title, dimensions)
  - `.pristine/` snapshot for diff comparison
- **Diff**: Compare edited SML against pristine state and generate `batchUpdate` JSON
- **Push**: Apply changes to Google Slides via the API
- **Copy-based workflow**: Duplicate elements by repeating XML with same ID but only x,y coordinates (omit w,h to signal copy)
  - Cross-slide and same-slide copy detection
  - Translation-based positioning
  - Full shape support including images with native dimensions
  - Unique suffix generation to prevent ID collisions
- **Supported operations**:
  - Text replacement and modification
  - Element copying with position translation
  - Content alignment extraction and application
- Async transport-based architecture with `GoogleSlidesTransport` and `LocalFileTransport` for testing
- Golden file testing infrastructure
