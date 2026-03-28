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
    return {
        "insertText": {
            "location": {
                "index": index,
                "tabId": tab_id,
            },
            "text": text,
        }
    }


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
) -> dict[str, Any]:
    return {
        "deleteContentRange": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            }
        }
    }


def bullet_preset_for_kind(kind: str) -> str:
    if kind == "NUMBERED":
        return "NUMBERED_DECIMAL_ALPHA_ROMAN"
    if kind == "CHECKBOX":
        return "BULLET_CHECKBOX"
    return "BULLET_DISC_CIRCLE_SQUARE"
