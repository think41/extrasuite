"""Typed request-construction helpers for ``reconcile_v2`` lowering."""

from __future__ import annotations

from typing import Any


def make_update_paragraph_role(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    role: str,
) -> dict[str, Any]:
    return {
        "updateParagraphStyle": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            },
            "paragraphStyle": {
                "namedStyleType": role,
            },
            "fields": "namedStyleType",
        }
    }


def make_insert_text(*, index: int, tab_id: str, text: str) -> dict[str, Any]:
    return make_insert_text_in_story(
        index=index,
        tab_id=tab_id,
        segment_id=None,
        text=text,
    )


def make_create_paragraph_bullets(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    bullet_preset: str,
) -> dict[str, Any]:
    return {
        "createParagraphBullets": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            },
            "bulletPreset": bullet_preset,
        }
    }


def make_delete_paragraph_bullets(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "deleteParagraphBullets": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            }
        }
    }


def make_insert_section_break(
    *,
    index: int,
    tab_id: str,
    section_type: str = "NEXT_PAGE",
) -> dict[str, Any]:
    return {
        "insertSectionBreak": {
            "location": {
                "index": index,
                "tabId": tab_id,
            },
            "sectionType": section_type,
        }
    }


def make_delete_content_range(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    segment_id: str | None = None,
) -> dict[str, Any]:
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
        "tabId": tab_id,
    }
    if segment_id:
        range_["segmentId"] = segment_id
    return {
        "deleteContentRange": {
            "range": range_,
        }
    }


def make_insert_text_in_story(
    *,
    index: int,
    tab_id: str,
    segment_id: str | None,
    text: str,
) -> dict[str, Any]:
    location: dict[str, Any] = {
        "index": index,
        "tabId": tab_id,
    }
    if segment_id:
        location["segmentId"] = segment_id
    return {
        "insertText": {
            "location": location,
            "text": text,
        }
    }


def make_delete_named_range(*, name: str) -> dict[str, Any]:
    return {"deleteNamedRange": {"name": name}}


def make_create_named_range(
    *,
    name: str,
    start_index: int,
    end_index: int,
    tab_id: str,
    segment_id: str | None = None,
) -> dict[str, Any]:
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
        "tabId": tab_id,
    }
    if segment_id:
        range_["segmentId"] = segment_id
    return {"createNamedRange": {"name": name, "range": range_}}


def bullet_preset_for_kind(kind: str) -> str:
    if kind == "NUMBERED":
        return "NUMBERED_DECIMAL_ALPHA_ROMAN"
    if kind == "CHECKBOX":
        return "BULLET_CHECKBOX"
    return "BULLET_DISC_CIRCLE_SQUARE"
