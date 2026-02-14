"""Bullet list operations for the mock Google Docs API."""

from __future__ import annotations

import uuid
from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_paragraphs_in_range, get_tab, validate_range

# Bullet preset to glyph symbol mappings for first nesting level
_BULLET_PRESETS: dict[str, list[str]] = {
    "BULLET_DISC_CIRCLE_SQUARE": ["●", "○", "■"],
    "BULLET_DIAMONDX_ARROW3D_SQUARE": ["❖", "➢", "■"],
    "BULLET_CHECKBOX": ["☐", "☐", "☐"],
    "BULLET_ARROW_DIAMOND_DISC": ["➔", "◆", "●"],
    "BULLET_STAR_CIRCLE_SQUARE": ["★", "○", "■"],
    "BULLET_ARROW3D_CIRCLE_SQUARE": ["➢", "○", "■"],
    "BULLET_LEFTTRIANGLE_DIAMOND_DISC": ["◀", "◆", "●"],
    "NUMBERED_DECIMAL_ALPHA_ROMAN": [],
    "NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS": [],
    "NUMBERED_DECIMAL_NESTED": [],
    "NUMBERED_UPPERALPHA_ALPHA_ROMAN": [],
    "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL": [],
    "NUMBERED_ZERODECIMAL_ALPHA_ROMAN": [],
}


def handle_create_paragraph_bullets(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle CreateParagraphBulletsRequest.

    Bug fixes applied:
    - Copy bold/italic/fontSize from first text run into bullet.textStyle
    - Reset namedStyleType to NORMAL_TEXT when creating bullets on heading
    """
    range_obj = request.get("range")
    bullet_preset = request.get("bulletPreset")

    if not range_obj:
        raise ValidationError("range is required")
    if not bullet_preset:
        raise ValidationError("bulletPreset is required")

    start_index = range_obj["startIndex"]
    end_index = range_obj["endIndex"]
    tab_id = range_obj.get("tabId")

    tab = get_tab(document, tab_id)
    validate_range(tab, start_index, end_index)

    list_id = f"kix.{uuid.uuid4().hex[:16]}"

    glyphs = _BULLET_PRESETS.get(bullet_preset, ["●", "○", "■"])
    is_numbered = bullet_preset.startswith("NUMBERED_")
    is_checkbox = bullet_preset == "BULLET_CHECKBOX"
    nesting_levels: list[dict[str, Any]] = []
    for level in range(9):
        level_def: dict[str, Any] = {
            "bulletAlignment": "START",
            "indentFirstLine": {"magnitude": 18 + level * 36, "unit": "PT"},
            "indentStart": {"magnitude": 36 + level * 36, "unit": "PT"},
            "textStyle": {"underline": False},
            "startNumber": 1,
        }
        if is_numbered:
            level_def["glyphType"] = (
                ["DECIMAL", "ALPHA", "ROMAN"][level % 3]
                if bullet_preset == "NUMBERED_DECIMAL_ALPHA_ROMAN"
                else "DECIMAL"
            )
            level_def["glyphFormat"] = f"%{level}."
        elif is_checkbox:
            level_def["glyphType"] = "GLYPH_TYPE_UNSPECIFIED"
            level_def["glyphFormat"] = f"%{level}"
        else:
            glyph_idx = level % len(glyphs) if glyphs else 0
            level_def["glyphSymbol"] = glyphs[glyph_idx] if glyphs else "●"
            level_def["glyphFormat"] = f"%{level}"
        nesting_levels.append(level_def)

    # Add list definition to document
    document_tab = tab.get("documentTab", {})
    lists = document_tab.setdefault("lists", {})
    lists[list_id] = {"listProperties": {"nestingLevels": nesting_levels}}

    # Heading styles that are inherently bold in Google Docs
    _bold_headings = {"HEADING_1", "HEADING_2", "TITLE"}

    # Apply bullet to each paragraph in range
    for paragraph in get_paragraphs_in_range(tab, start_index, end_index):
        # Build bullet textStyle — inherit bold from first non-empty text run.
        # For inherently-bold headings (HEADING_1, HEADING_2, TITLE), always
        # set bold regardless of text run styles.
        # The real API also copies italic when it was explicitly set via
        # updateTextStyle.
        bullet_text_style: dict[str, Any] = {}
        ps = paragraph.get("paragraphStyle", {})
        named_style = ps.get("namedStyleType", "")

        if named_style in _bold_headings:
            bullet_text_style["bold"] = True
        else:
            first_elements = paragraph.get("elements", [])
            for elem in first_elements:
                tr = elem.get("textRun")
                if tr and tr.get("content", "").strip():
                    if tr.get("textStyle", {}).get("bold"):
                        bullet_text_style["bold"] = True
                    break

        # Copy italic only when explicitly set via updateTextStyle
        first_elements = paragraph.get("elements", [])
        for elem in first_elements:
            tr = elem.get("textRun")
            if tr and tr.get("content", "").strip():
                src_style = tr.get("textStyle", {})
                explicit = set(src_style.get("__explicit__", []))
                if src_style.get("italic") and "italic" in explicit:
                    bullet_text_style["italic"] = True
                break

        paragraph["bullet"] = {
            "listId": list_id,
            "textStyle": bullet_text_style,
        }

        # Set bullet indentation on paragraph style
        ps = paragraph.setdefault("paragraphStyle", {})
        ps["indentFirstLine"] = {"magnitude": 18, "unit": "PT"}
        ps["indentStart"] = {"magnitude": 36, "unit": "PT"}

    return {}


def handle_delete_paragraph_bullets(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeleteParagraphBulletsRequest.

    Bug fix: Remove indentFirstLine/indentStart entirely instead of
    setting them to {unit: "PT"}.
    """
    range_obj = request.get("range")
    if not range_obj:
        raise ValidationError("range is required")

    start_index = range_obj["startIndex"]
    end_index = range_obj["endIndex"]
    tab_id = range_obj.get("tabId")

    tab = get_tab(document, tab_id)
    validate_range(tab, start_index, end_index)

    for paragraph in get_paragraphs_in_range(tab, start_index, end_index):
        paragraph.pop("bullet", None)
        ps = paragraph.get("paragraphStyle", {})
        ps.pop("indentStart", None)
        ps.pop("indentFirstLine", None)

    return {}
