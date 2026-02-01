# Copy-Based Workflow Implementation Plan

## Test Presentation
URL: https://docs.google.com/presentation/d/1Lx-IV2QL1jfU1V_JQ1vvAB_4u8iW0ItwRkIFbQRqvys/edit

## Success Criteria
Copy slide 10 and slide 27 to new slides → thumbnails should look identical

---

## Phase 1: Core Format Changes

- [ ] 1.1 Add `<Slide>` root tag to content_generator.py
- [ ] 1.2 Add absolute positions for ALL elements (not just roots)
- [ ] 1.3 Remove patterns from content_generator.py and slide_processor.py
- [ ] 1.4 Delete patterns.py
- [ ] 1.5 Expand shape type mappings in content_generator.py
- [ ] 1.6 Update content_parser.py to expect `<Slide>` root

## Phase 2: Copy Logic

- [ ] 2.1 Update content_diff.py for new copy detection (missing w/h = copy)
- [ ] 2.2 Update content_requests.py for translation-based child positioning
- [ ] 2.3 Expand shape types in content_requests.py (_tag_to_type, _create_shape_request)

## Phase 3: Style Resolution

- [ ] 3.1 Parse theme data in slide_processor.py
- [ ] 3.2 Implement font resolution in style_extractor.py
- [ ] 3.3 Implement color resolution (theme colors → hex)

## Phase 4: Text Styling

- [ ] 4.1 Update content_requests.py for per-run text styling

## Phase 5: Cleanup

- [ ] 5.1 Delete old code files (client.py, diff.py, generator.py, parser.py, requests.py, compression.py, classes.py, overview.py)
- [ ] 5.2 Rename client_v2.py → client.py, SlidesClientV2 → SlidesClient
- [ ] 5.3 Update __init__.py exports

## Phase 6: Documentation

- [ ] 6.1 Rewrite SKILL.md for copy workflow
- [ ] 6.2 Update extraslide/CLAUDE.md
- [ ] 6.3 Update copy-workflow.md with new conventions

## Phase 7: Testing

- [ ] 7.1 Pull test presentation
- [ ] 7.2 Copy slide 10 to new slide, push, compare thumbnails
- [ ] 7.3 Copy slide 27 to new slide, push, compare thumbnails
- [ ] 7.4 Iterate until pixel-perfect

---

## Implementation Notes

### Copy Convention
- Root of copy: only x, y (no w, h)
- Children: unchanged from original
- Diff calculates translation from root position delta

### Shape Types to Support
Full Google Slides spectrum - see plan for complete list.

### Theme Resolution
- Resolve fonts from theme bodyFont/titleFont
- Resolve colors from theme colorScheme (ACCENT1 → hex)

### Known API Limitations
- Autofit cannot be set
- Image crop/effects cannot be set

---

## Progress Log

### [Date] - Session Start
- Created implementation plan
- Starting Phase 1

