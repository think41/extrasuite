"""Text and paragraph style operations for the mock Google Docs API."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_paragraphs_in_range, get_tab, validate_range

# Default values for text style fields - the real API omits these
_TEXT_STYLE_DEFAULTS: dict[str, Any] = {
    "bold": False,
    "italic": False,
    "underline": False,
    "strikethrough": False,
    "smallCaps": False,
    "baselineOffset": "NONE",
}


def _apply_text_style_to_ts(
    ts: dict[str, Any],
    text_style: dict[str, Any],
    field_list: list[str],
) -> None:
    """Apply text style fields to a textStyle dict, omitting defaults."""
    for field in field_list:
        if field in text_style:
            value = text_style[field]
            if _TEXT_STYLE_DEFAULTS.get(field) == value:
                ts.pop(field, None)
            else:
                ts[field] = value
        else:
            ts.pop(field, None)


def handle_update_text_style(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateTextStyleRequest."""
    range_obj = request.get("range")
    text_style = request.get("textStyle")
    fields = request.get("fields")

    if not range_obj:
        raise ValidationError("range is required")
    if text_style is None:
        raise ValidationError("textStyle is required")
    if not fields:
        raise ValidationError("fields is required")

    start_index = range_obj["startIndex"]
    end_index = range_obj["endIndex"]
    tab_id = range_obj.get("tabId")

    tab = get_tab(document, tab_id)
    validate_range(tab, start_index, end_index)

    field_list = [f.strip() for f in fields.split(",")]

    for paragraph in get_paragraphs_in_range(tab, start_index, end_index):
        elements = paragraph.get("elements", [])
        new_elements: list[dict[str, Any]] = []

        for element in elements:
            el_start = element.get("startIndex", 0)
            el_end = element.get("endIndex", 0)
            text_run = element.get("textRun")

            if el_end <= start_index or el_start >= end_index or not text_run:
                new_elements.append(element)
                continue

            content = text_run.get("content", "")
            old_style = text_run.get("textStyle", {})

            split_start = max(start_index, el_start) - el_start
            split_end = min(end_index, el_end) - el_start

            # Before part (unchanged)
            if split_start > 0:
                before_text = content[:split_start]
                new_elements.append(
                    {
                        "startIndex": el_start,
                        "endIndex": el_start + split_start,
                        "textRun": {
                            "content": before_text,
                            "textStyle": dict(old_style),
                        },
                    }
                )

            # Middle part (styled)
            middle_text = content[split_start:split_end]
            middle_style = copy.deepcopy(old_style)
            _apply_text_style_to_ts(middle_style, text_style, field_list)
            # Track which fields were explicitly set via updateTextStyle
            existing_explicit = set(middle_style.get("__explicit__", []))
            existing_explicit.update(f for f in field_list if f in text_style)
            # Remove fields that were cleared (in field_list but not in text_style)
            existing_explicit -= {f for f in field_list if f not in text_style}
            middle_style["__explicit__"] = sorted(existing_explicit)
            new_elements.append(
                {
                    "startIndex": el_start + split_start,
                    "endIndex": el_start + split_end,
                    "textRun": {
                        "content": middle_text,
                        "textStyle": middle_style,
                    },
                }
            )

            # After part - merge trailing \n into middle if no link
            has_link = "link" in text_style and text_style["link"]
            if split_end < len(content):
                after_text = content[split_end:]
                if after_text == "\n" and not has_link:
                    mid_el = new_elements[-1]
                    mid_el["endIndex"] = el_end
                    mid_el["textRun"]["content"] += "\n"
                else:
                    new_elements.append(
                        {
                            "startIndex": el_start + split_end,
                            "endIndex": el_end,
                            "textRun": {
                                "content": after_text,
                                "textStyle": dict(old_style),
                            },
                        }
                    )

        paragraph["elements"] = new_elements

    # Link auto-styling
    _link_blue = {
        "color": {
            "rgbColor": {
                "red": 0.06666667,
                "green": 0.33333334,
                "blue": 0.8,
            }
        }
    }
    if "link" in field_list:
        if text_style.get("link"):
            for paragraph in get_paragraphs_in_range(tab, start_index, end_index):
                for element in paragraph.get("elements", []):
                    el_start = element.get("startIndex", 0)
                    el_end = element.get("endIndex", 0)
                    if el_end <= start_index or el_start >= end_index:
                        continue
                    text_run = element.get("textRun")
                    if not text_run:
                        continue
                    ts = text_run.get("textStyle", {})
                    if "link" in ts:
                        ts.setdefault("underline", True)
                        ts.setdefault("foregroundColor", _link_blue)
        else:
            for paragraph in get_paragraphs_in_range(tab, start_index, end_index):
                for element in paragraph.get("elements", []):
                    el_start = element.get("startIndex", 0)
                    el_end = element.get("endIndex", 0)
                    if el_end <= start_index or el_start >= end_index:
                        continue
                    text_run = element.get("textRun")
                    if not text_run:
                        continue
                    ts = text_run.get("textStyle", {})
                    fc = ts.get("foregroundColor", {})
                    if fc == _link_blue:
                        ts.pop("foregroundColor", None)

    # Update bullet.textStyle for affected bulleted paragraphs.
    # The real API rebuilds bullet.textStyle from the text runs' bold state
    # when "bold" is being changed.
    #
    # For non-heading paragraphs: checks the first non-empty text run.
    # For heading paragraphs: checks ALL non-empty text runs — only sets
    # bullet.textStyle.bold if every non-empty run has bold.
    _heading_names = {
        "HEADING_1",
        "HEADING_2",
        "HEADING_3",
        "HEADING_4",
        "HEADING_5",
        "HEADING_6",
    }
    if "bold" in field_list:
        for paragraph in get_paragraphs_in_range(tab, start_index, end_index):
            bullet = paragraph.get("bullet")
            if not bullet:
                continue
            ps = paragraph.get("paragraphStyle", {})
            is_heading = ps.get("namedStyleType", "") in _heading_names
            # Rebuild bullet.textStyle from scratch — real API replaces, not merges
            if is_heading:
                # Headings: ALL non-empty runs must have bold
                non_empty_runs = [
                    elem.get("textRun")
                    for elem in paragraph.get("elements", [])
                    if elem.get("textRun")
                    and elem["textRun"].get("content", "").strip()
                ]
                has_bold = bool(non_empty_runs) and all(
                    tr.get("textStyle", {}).get("bold") for tr in non_empty_runs
                )
            else:
                # Non-headings: check first non-empty run only
                has_bold = False
                for elem in paragraph.get("elements", []):
                    tr = elem.get("textRun")
                    if tr and tr.get("content", "").strip():
                        if tr.get("textStyle", {}).get("bold"):
                            has_bold = True
                        break
            bullet["textStyle"] = {"bold": True} if has_bold else {}

    # Run consolidation is now handled by normalize_segment in reindex pass
    return {}


def handle_update_paragraph_style(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateParagraphStyleRequest."""
    range_obj = request.get("range")
    paragraph_style = request.get("paragraphStyle")
    fields = request.get("fields")

    if not range_obj:
        raise ValidationError("range is required")
    if paragraph_style is None:
        raise ValidationError("paragraphStyle is required")
    if not fields:
        raise ValidationError("fields is required")

    start_index = range_obj["startIndex"]
    end_index = range_obj["endIndex"]
    tab_id = range_obj.get("tabId")

    tab = get_tab(document, tab_id)
    validate_range(tab, start_index, end_index)

    field_list = [f.strip() for f in fields.split(",")]

    _named_style_defaults: dict[str, Any] = {
        "direction": "LEFT_TO_RIGHT",
    }
    has_named_style = "namedStyleType" in paragraph_style

    _heading_styles = {
        "HEADING_1",
        "HEADING_2",
        "HEADING_3",
        "HEADING_4",
        "HEADING_5",
        "HEADING_6",
    }

    for paragraph in get_paragraphs_in_range(tab, start_index, end_index):
        ps = paragraph.setdefault("paragraphStyle", {})
        for field in field_list:
            if field in paragraph_style:
                ps[field] = paragraph_style[field]
            elif has_named_style and field in _named_style_defaults:
                ps.setdefault(field, _named_style_defaults[field])
            else:
                ps.pop(field, None)

        named_style = ps.get("namedStyleType", "")
        is_setting_heading = (
            "namedStyleType" in field_list and named_style in _heading_styles
        )
        if named_style in _heading_styles:
            if "headingId" not in ps:
                ps["headingId"] = f"h.{uuid.uuid4().hex[:16]}"
            if is_setting_heading:
                # When setting a heading style, the real API:
                # 1. Clears bullet.textStyle to {}
                # 2. Removes bold, italic, underline from all text runs
                #    (headings are bold by default; the real API also clears
                #    italic/underline that were inherited during insertText,
                #    though it preserves ones set via updateTextStyle — we
                #    can't distinguish these, so we clear all three)
                bullet = paragraph.get("bullet")
                if bullet:
                    bullet["textStyle"] = {}
                for elem in paragraph.get("elements", []):
                    tr = elem.get("textRun")
                    if tr:
                        ts = tr.get("textStyle", {})
                        explicit = set(ts.get("__explicit__", []))
                        # Bold is always cleared (headings are bold by default).
                        # Italic/underline are only cleared if NOT explicitly
                        # set via updateTextStyle. The real API also preserves
                        # I/U from the original document, but we can't track
                        # provenance for pre-existing styles (only for styles
                        # set via updateTextStyle during this mock session).
                        ts.pop("bold", None)
                        if "italic" not in explicit:
                            ts.pop("italic", None)
                        if "underline" not in explicit:
                            ts.pop("underline", None)
        else:
            ps.pop("headingId", None)

    return {}
