# Copy-Based Workflow Implementation Plan

## Test Presentation
URL: https://docs.google.com/presentation/d/1Lx-IV2QL1jfU1V_JQ1vvAB_4u8iW0ItwRkIFbQRqvys/edit

## Success Criteria
Copy slide 10 and slide 27 to new slides → thumbnails should look identical

---

## Phase 1: Core Format Changes ✅ COMPLETED

- [x] 1.1 Add `<Slide>` root tag to content_generator.py
- [x] 1.2 Add absolute positions for ALL elements (not just roots)
- [x] 1.3 Remove patterns from content_generator.py and slide_processor.py
- [x] 1.4 Delete patterns.py
- [x] 1.5 Expand shape type mappings in content_generator.py (100+ shapes)
- [x] 1.6 Update content_parser.py to expect `<Slide>` root

## Phase 2: Copy Logic ✅ COMPLETED

- [x] 2.1 Update content_diff.py for new copy detection (missing w/h = copy)
- [x] 2.2 Update content_requests.py for translation-based child positioning
- [x] 2.3 Expand shape types in content_requests.py (_tag_to_type, _create_shape_request)
- [x] 2.4 Add unique suffix to slide IDs to prevent collisions

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

## Phase 6: Documentation ✅ COMPLETED

- [ ] 6.1 Rewrite SKILL.md for copy workflow (deferred - skill distributed by server)
- [x] 6.2 Update extraslide/CLAUDE.md
- [x] 6.3 Update copy-workflow.md with new conventions

## Phase 7: Testing ✅ COMPLETED

- [x] 7.1 Pull test presentation
- [x] 7.2 Copy slide element to new slide, push successfully
- [x] 7.3 Verify element created with correct position, size, and styling
- [x] 7.4 Full slide 27 copy test - thumbnails visually identical (245 changes applied)

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

### 2026-02-01 - Major Progress

**Phase 1 Complete:**
- Added `<Slide>` root tag for valid XML
- All elements now have absolute x, y, w, h positions
- Removed patterns feature entirely (deleted patterns.py)
- Expanded shape type mappings (100+ Google Slides shapes)

**Phase 2 Complete:**
- Copy detection by missing w/h convention works
- Translation-based child positioning verified
- Expanded _tag_to_type and _create_shape_request mappings
- Added unique suffix to slide IDs to prevent collisions

**Phase 7 Initial Testing:**
- Pulled test presentation with new format
- Created copy of e558 (RoundRect) at new position (50, 100)
- Pushed successfully - 8 changes applied
- Verified: new slide 28 created with correct position, size, styling, and text

**Full Slide Copy Verified:**
- Copied slide 27 to slide 30 (245 API changes)
- Fetched thumbnails for both slides
- Visual comparison: virtually identical
- File sizes: 313KB vs 313KB (~0.04% difference)

**Phase 6 Documentation Complete:**
- Updated copy-workflow.md with new copy convention (x,y only, no w,h)
- Updated extraslide/CLAUDE.md with V2 client architecture
- Documented translation-based position calculation

**Remaining (Nice to Have):**
- Phase 3: Theme/style resolution (font/color from theme)
- Phase 4: Per-run text styling

