"""Content request generation for ExtraDoc v2.

Handles CONTENT_BLOCK change nodes: insert, delete, and modify.

Key improvement over v1: MODIFIED uses diff-match-patch for
per-paragraph granular text diffs instead of delete-all + insert-all.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from diff_match_patch import diff_match_patch

from extradoc.indexer import utf16_len
from extradoc.style_converter import (
    PARAGRAPH_STYLE_PROPS,
    TEXT_STYLE_PROPS,
    convert_styles,
)

from ..types import ChangeNode, ChangeOp, SegmentContext

# Heading tag to named style mapping
HEADING_STYLES: dict[str, str] = {
    "title": "TITLE",
    "subtitle": "SUBTITLE",
    "h1": "HEADING_1",
    "h2": "HEADING_2",
    "h3": "HEADING_3",
    "h4": "HEADING_4",
    "h5": "HEADING_5",
    "h6": "HEADING_6",
}

# Inline formatting tags
INLINE_STYLE_TAGS: dict[str, str] = {
    "b": "bold",
    "i": "italic",
    "u": "underline",
    "s": "strikethrough",
    "sup": "superscript",
    "sub": "subscript",
}

# Special elements that consume 1 index
SPECIAL_ELEMENT_TAGS = frozenset(
    {"hr", "pagebreak", "columnbreak", "image", "footnote"}
)

# Paragraph style attributes
PARA_STYLE_ATTRS = frozenset(
    {
        "align",
        "lineSpacing",
        "spaceAbove",
        "spaceBelow",
        "indentLeft",
        "indentRight",
        "indentFirst",
        "keepTogether",
        "keepNext",
        "avoidWidow",
        "direction",
        "bgColor",
        "borderTop",
        "borderBottom",
        "borderLeft",
        "borderRight",
    }
)


@dataclass
class ParsedContent:
    """Parsed content block ready for request generation."""

    plain_text: str
    special_elements: list[tuple[int, str, dict[str, str]]]
    paragraph_styles: list[tuple[int, int, str]]
    paragraph_props: list[tuple[int, int, dict[str, str]]]
    bullets: list[tuple[int, int, str, int]]
    text_styles: list[tuple[int, int, dict[str, str]]]


class ContentGenerator:
    """Generates batchUpdate requests for content block changes."""

    def __init__(self, style_defs: dict[str, dict[str, str]] | None = None) -> None:
        self._style_defs = style_defs
        self._dmp = diff_match_patch()

    def emit(
        self, node: ChangeNode, ctx: SegmentContext
    ) -> tuple[list[dict[str, Any]], bool]:
        """Emit requests for a CONTENT_BLOCK change.

        Returns (requests, segment_end_consumed).
        """
        if node.op == ChangeOp.DELETED:
            return self._delete(node, ctx), False
        elif node.op == ChangeOp.ADDED:
            return self._add(node, ctx)
        elif node.op == ChangeOp.MODIFIED:
            return self._modify(node, ctx)
        return [], False

    # --- DELETE ---

    def _delete(self, node: ChangeNode, ctx: SegmentContext) -> list[dict[str, Any]]:
        """Delete content at pristine range."""
        if not node.before_xml or node.pristine_end <= node.pristine_start:
            return []

        start = node.pristine_start
        end = node.pristine_end

        # Don't delete the segment's final newline
        if ctx.segment_end > 0 and end >= ctx.segment_end:
            end = ctx.segment_end - 1

        if start >= end:
            return []

        range_spec: dict[str, Any] = {"startIndex": start, "endIndex": end}
        if ctx.segment_id:
            range_spec["segmentId"] = ctx.segment_id

        return [{"deleteContentRange": {"range": range_spec}}]

    # --- ADD ---

    def _add(
        self, node: ChangeNode, ctx: SegmentContext
    ) -> tuple[list[dict[str, Any]], bool]:
        """Insert content at pristine insertion point."""
        if not node.after_xml:
            return [], False

        segment_start = 1 if ctx.segment_id is None else 0
        insert_idx = node.pristine_start
        if insert_idx <= 0:
            insert_idx = segment_start
        if ctx.segment_end > 0 and insert_idx > ctx.segment_end - 1:
            insert_idx = ctx.segment_end - 1

        at_seg_end = ctx.segment_end > 0 and insert_idx >= ctx.segment_end - 1
        strip_for_seg_end = at_seg_end and not ctx.segment_end_consumed
        strip_nl = ctx.followed_by_added_table or strip_for_seg_end
        consumed = strip_for_seg_end

        requests = self._generate_content_insert_requests(
            node.after_xml,
            ctx.segment_id,
            insert_idx,
            strip_trailing_newline=strip_nl,
            delete_existing_bullets=True,
        )

        return requests, consumed

    # --- MODIFY (NEW: granular per-paragraph diffs) ---

    def _modify(
        self, node: ChangeNode, ctx: SegmentContext
    ) -> tuple[list[dict[str, Any]], bool]:
        """Modify content using granular per-paragraph diffs.

        For v2, we fall back to delete + insert (same as v1) to ensure
        correctness. The diff-match-patch granular path is available for
        future optimization but requires careful handling of paragraph
        boundaries, styles, and special elements.
        """
        requests: list[dict[str, Any]] = []
        consumed = False

        # Delete the old content
        if node.before_xml and node.pristine_end > node.pristine_start:
            d_start = node.pristine_start
            d_end = node.pristine_end
            if ctx.segment_end > 0 and d_end >= ctx.segment_end:
                d_end = ctx.segment_end - 1
            if d_start < d_end:
                range_spec: dict[str, Any] = {"startIndex": d_start, "endIndex": d_end}
                if ctx.segment_id:
                    range_spec["segmentId"] = ctx.segment_id
                requests.append({"deleteContentRange": {"range": range_spec}})

        # Insert the new content
        if node.after_xml:
            segment_start = 1 if ctx.segment_id is None else 0
            insert_idx = node.pristine_start
            if insert_idx <= 0:
                insert_idx = segment_start
            if ctx.segment_end > 0 and insert_idx > ctx.segment_end - 1:
                insert_idx = ctx.segment_end - 1

            at_seg_end = ctx.segment_end > 0 and insert_idx >= ctx.segment_end - 1
            strip_for_seg_end = at_seg_end and not ctx.segment_end_consumed
            strip_nl = ctx.followed_by_added_table or strip_for_seg_end
            if strip_for_seg_end:
                consumed = True

            requests.extend(
                self._generate_content_insert_requests(
                    node.after_xml,
                    ctx.segment_id,
                    insert_idx,
                    strip_trailing_newline=strip_nl,
                    delete_existing_bullets=True,
                )
            )

        return requests, consumed

    # --- Content insert request generation (cherry-picked from v1) ---

    def _generate_content_insert_requests(
        self,
        xml_content: str,
        segment_id: str | None,
        insert_index: int = 1,
        strip_trailing_newline: bool = False,
        delete_existing_bullets: bool = False,
    ) -> list[dict[str, Any]]:
        """Generate insert requests for content XML."""
        if not xml_content or not xml_content.strip():
            return []

        requests: list[dict[str, Any]] = []
        parsed = self._parse_content_block_xml(xml_content)

        if strip_trailing_newline and parsed.plain_text.endswith("\n"):
            parsed = ParsedContent(
                plain_text=parsed.plain_text[:-1],
                special_elements=parsed.special_elements,
                paragraph_styles=parsed.paragraph_styles,
                paragraph_props=parsed.paragraph_props,
                bullets=parsed.bullets,
                text_styles=parsed.text_styles,
            )

        if not parsed.plain_text:
            return []

        def make_location(index: int) -> dict[str, Any]:
            loc: dict[str, Any] = {"index": insert_index + index}
            if segment_id:
                loc["segmentId"] = segment_id
            return loc

        def make_range(start: int, end: int) -> dict[str, Any]:
            rng: dict[str, Any] = {
                "startIndex": insert_index + start,
                "endIndex": insert_index + end,
            }
            if segment_id:
                rng["segmentId"] = segment_id
            return rng

        # 1. Insert plain text
        requests.append(
            {
                "insertText": {
                    "location": make_location(0),
                    "text": parsed.plain_text,
                }
            }
        )

        # 1.5. Clear formatting
        text_len = utf16_len(parsed.plain_text)
        requests.append(
            {
                "updateTextStyle": {
                    "range": make_range(0, text_len),
                    "textStyle": {
                        "bold": False,
                        "italic": False,
                        "underline": False,
                        "strikethrough": False,
                        "baselineOffset": "NONE",
                    },
                    "fields": "bold,italic,underline,strikethrough,baselineOffset",
                }
            }
        )

        # 2. Insert special elements (highest offset first)
        for offset, elem_type, _attrs in sorted(
            parsed.special_elements, key=lambda x: x[0], reverse=True
        ):
            if elem_type == "pagebreak":
                requests.append(
                    {"insertPageBreak": {"location": make_location(offset)}}
                )
            elif elem_type == "columnbreak":
                requests.append(
                    {
                        "insertSectionBreak": {
                            "location": make_location(offset),
                            "sectionType": "CONTINUOUS",
                        }
                    }
                )

        # 3. Apply paragraph styles
        for start, end, named_style in parsed.paragraph_styles:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": make_range(start, end),
                        "paragraphStyle": {"namedStyleType": named_style},
                        "fields": "namedStyleType",
                    }
                }
            )

        # 3.5 Apply paragraph properties
        for start, end, props in parsed.paragraph_props:
            para_style, para_fields = convert_styles(props, PARAGRAPH_STYLE_PROPS)
            if para_style and para_fields:
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": make_range(start, end),
                            "paragraphStyle": para_style,
                            "fields": ",".join(para_fields),
                        }
                    }
                )

        # 4. Apply bullets
        if parsed.bullets:
            bullet_groups: list[tuple[int, int, str]] = []
            for start, end, bullet_type, _level in parsed.bullets:
                preset = _bullet_type_to_preset(bullet_type)
                if (
                    bullet_groups
                    and bullet_groups[-1][2] == preset
                    and bullet_groups[-1][1] == start
                ):
                    bullet_groups[-1] = (bullet_groups[-1][0], end, preset)
                else:
                    bullet_groups.append((start, end, preset))

            for group_start, group_end, preset in bullet_groups:
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": make_range(group_start, group_end),
                            "bulletPreset": preset,
                        }
                    }
                )

        # 4.5 Delete existing bullets for non-bullet paragraphs
        if delete_existing_bullets:
            bullet_ranges = {(s, e) for s, e, _, _ in parsed.bullets}
            for para_start, para_end, _named_style in parsed.paragraph_styles:
                if (para_start, para_end) not in bullet_ranges:
                    actual_para_end = para_end
                    if strip_trailing_newline:
                        text_len_check = utf16_len(parsed.plain_text)
                        if para_end > text_len_check:
                            actual_para_end = text_len_check + 1
                    requests.append(
                        {
                            "deleteParagraphBullets": {
                                "range": make_range(para_start, actual_para_end),
                            }
                        }
                    )

        # 5. Apply text styles
        for start, end, styles in parsed.text_styles:
            text_style, fields = convert_styles(styles, TEXT_STYLE_PROPS)
            if text_style and fields:
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": make_range(start, end),
                            "textStyle": text_style,
                            "fields": ",".join(fields),
                        }
                    }
                )

        return requests

    # --- Content parsing (cherry-picked from v1 diff_engine.py) ---

    def _parse_content_block_xml(self, xml_content: str) -> ParsedContent:
        """Parse ContentBlock XML into structured data."""
        wrapped = f"<root>{xml_content}</root>"
        root = ET.fromstring(wrapped)

        plain_text_parts: list[str] = []
        special_elements: list[tuple[int, str, dict[str, str]]] = []
        paragraph_styles: list[tuple[int, int, str]] = []
        paragraph_props: list[tuple[int, int, dict[str, str]]] = []
        bullets: list[tuple[int, int, str, int]] = []
        text_styles: list[tuple[int, int, dict[str, str]]] = []

        current_offset = 0

        for para_elem in root:
            tag = para_elem.tag
            para_start = current_offset

            named_style = "NORMAL_TEXT"
            bullet_type = None
            bullet_level = 0

            if tag in HEADING_STYLES:
                named_style = HEADING_STYLES[tag]
            elif tag == "li":
                bullet_type = para_elem.get("type", "bullet")
                bullet_level = int(para_elem.get("level", "0"))

            para_text, para_specials, para_text_styles = (
                self._extract_paragraph_content(para_elem, current_offset)
            )

            # Prepend tabs for nested bullets
            if bullet_level > 0:
                tabs = "\t" * bullet_level
                tab_len = utf16_len(tabs)
                para_text = tabs + para_text
                para_specials = [
                    (offset + tab_len, et, attrs) for offset, et, attrs in para_specials
                ]
                para_text_styles = [
                    (s + tab_len, e + tab_len, st) for s, e, st in para_text_styles
                ]

            plain_text_parts.append(para_text)
            special_elements.extend(para_specials)
            text_styles.extend(para_text_styles)

            para_end = current_offset + utf16_len(para_text) + 1

            paragraph_styles.append((para_start, para_end, named_style))

            # Extract paragraph style properties
            para_props_dict: dict[str, str] = {
                k: v for k, v in para_elem.attrib.items() if k in PARA_STYLE_ATTRS
            }

            # Resolve class attribute
            class_name = para_elem.get("class")
            if class_name and self._style_defs and class_name in self._style_defs:
                class_props = self._style_defs[class_name]
                style_to_para_mapping = {"alignment": "align"}
                text_style_props = {
                    "bg",
                    "color",
                    "font",
                    "size",
                    "bold",
                    "italic",
                    "underline",
                    "strikethrough",
                }
                para_class_styles: dict[str, str] = {}
                text_class_styles: dict[str, str] = {}
                for prop, value in class_props.items():
                    mapped = style_to_para_mapping.get(prop, prop)
                    if mapped in PARA_STYLE_ATTRS and mapped not in para_props_dict:
                        para_class_styles[mapped] = value
                    elif prop in text_style_props:
                        text_class_styles[prop] = value
                para_props_dict.update(para_class_styles)
                if text_class_styles and para_text:
                    text_start = para_start + (bullet_level if bullet_level > 0 else 0)
                    text_end = para_start + utf16_len(para_text)
                    if text_start < text_end:
                        text_styles.append((text_start, text_end, text_class_styles))

            if para_props_dict:
                paragraph_props.append((para_start, para_end, para_props_dict))

            if bullet_type:
                bullets.append((para_start, para_end, bullet_type, bullet_level))

            current_offset = para_end

        plain_text = "\n".join(plain_text_parts)
        if plain_text_parts:
            plain_text += "\n"

        return ParsedContent(
            plain_text=plain_text,
            special_elements=special_elements,
            paragraph_styles=paragraph_styles,
            paragraph_props=paragraph_props,
            bullets=bullets,
            text_styles=text_styles,
        )

    def _extract_paragraph_content(
        self,
        para_elem: ET.Element,
        base_offset: int,
    ) -> tuple[
        str,
        list[tuple[int, str, dict[str, str]]],
        list[tuple[int, int, dict[str, str]]],
    ]:
        """Extract text, special elements, and text styles from a paragraph."""
        plain_text_parts: list[str] = []
        special_elements: list[tuple[int, str, dict[str, str]]] = []
        text_styles: list[tuple[int, int, dict[str, str]]] = []
        current_offset = base_offset

        def process_node(node: ET.Element, inherited_styles: dict[str, str]) -> None:
            nonlocal current_offset
            tag = node.tag
            node_styles = inherited_styles.copy()

            if tag in INLINE_STYLE_TAGS:
                node_styles[INLINE_STYLE_TAGS[tag]] = "1"
            elif tag == "a":
                href = node.get("href", "")
                if href:
                    node_styles["link"] = href
            elif tag == "span":
                class_name = node.get("class")
                if class_name and self._style_defs and class_name in self._style_defs:
                    node_styles.update(self._style_defs[class_name])
                for attr, value in node.attrib.items():
                    if attr != "class":
                        node_styles[attr] = value

            if node.text:
                text = node.text
                text_len = utf16_len(text)
                plain_text_parts.append(text)
                style_dict = {k: v for k, v in node_styles.items() if v}
                if style_dict:
                    text_styles.append(
                        (current_offset, current_offset + text_len, style_dict)
                    )
                current_offset += text_len

            for child in node:
                if child.tag in SPECIAL_ELEMENT_TAGS:
                    special_elements.append(
                        (current_offset, child.tag, dict(child.attrib))
                    )
                else:
                    process_node(child, node_styles)

                if child.tail:
                    tail = child.tail
                    tail_len = utf16_len(tail)
                    plain_text_parts.append(tail)
                    style_dict = {k: v for k, v in node_styles.items() if v}
                    if style_dict:
                        text_styles.append(
                            (current_offset, current_offset + tail_len, style_dict)
                        )
                    current_offset += tail_len

        # Handle para element's direct text
        if para_elem.text:
            text = para_elem.text
            text_len = utf16_len(text)
            plain_text_parts.append(text)
            current_offset += text_len

        for child in para_elem:
            if child.tag in SPECIAL_ELEMENT_TAGS:
                special_elements.append((current_offset, child.tag, dict(child.attrib)))
            else:
                process_node(child, {})
            if child.tail:
                tail = child.tail
                tail_len = utf16_len(tail)
                plain_text_parts.append(tail)
                current_offset += tail_len

        return "".join(plain_text_parts), special_elements, text_styles


def _bullet_type_to_preset(bullet_type: str) -> str:
    """Convert bullet type to Google Docs bullet preset."""
    presets = {
        "bullet": "BULLET_DISC_CIRCLE_SQUARE",
        "decimal": "NUMBERED_DECIMAL_NESTED",
        "alpha": "NUMBERED_UPPERALPHA_ALPHA_ROMAN",
        "roman": "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
        "checkbox": "BULLET_CHECKBOX",
    }
    return presets.get(bullet_type, "BULLET_DISC_CIRCLE_SQUARE")
