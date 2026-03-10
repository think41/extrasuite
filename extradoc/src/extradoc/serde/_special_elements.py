"""Typed special elements for the markdown serde format.

These represent markdown constructs that have no direct Google Docs equivalent:
fenced code blocks, callout panels, and block quotations.

Each element:
  - Knows its canonical named range name (extradoc:<type>[:<variant>])
  - Knows how to build a styled 1×1 Google Docs Table (to_table)
  - Knows how to render itself as a markdown string (to_markdown)
  - Knows how to reconstruct itself from a named-range-annotated table (from_table)

Visual conventions:
  - Code block:       #f3f3f3 bg, Courier New 10pt font
  - Callout warning:  #fff3cd bg
  - Callout info:     #d1ecf1 bg
  - Callout danger:   #f8d7da bg
  - Callout tip:      #d4edda bg
  - Blockquote:       #f9f9f9 bg, 3pt left border #888888
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from extradoc.api_types._generated import (
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    StructuralElement,
    Table,
    TableCell,
    TableCellStyle,
    TableRow,
    TextRun,
    TextStyle,
)
from extradoc.serde._utils import hex_to_optional_color, str_to_cell_border


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_trailing_se() -> StructuralElement:
    """Return the mandatory trailing paragraph that table cells must end with."""
    return StructuralElement.model_validate(
        {
            "paragraph": {
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                },
                "elements": [{"textRun": {"content": "\n"}}],
            }
        }
    )


def _build_para(text: str, text_style: TextStyle | None = None) -> Paragraph:
    """Build a Paragraph with one text run (+ mandatory trailing \\n)."""
    elements: list[ParagraphElement] = []
    if text:
        elements.append(
            ParagraphElement(text_run=TextRun(content=text, text_style=text_style))
        )
    elements.append(ParagraphElement(text_run=TextRun(content="\n")))
    return Paragraph(
        elements=elements,
        paragraph_style=ParagraphStyle(
            named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
        ),
    )


def _make_1x1_table(
    paragraphs: list[Paragraph],
    *,
    bg_hex: str | None = None,
    border_left: str | None = None,
) -> Table:
    """Build a 1×1 Google Docs Table from a list of Paragraphs.

    Adds a trailing paragraph to the cell content if not already present.
    Applies background color and/or left border if specified.
    """
    content: list[StructuralElement] = [
        StructuralElement(paragraph=p) for p in paragraphs
    ]
    # Ensure cell ends with a trailing empty paragraph
    if not content:
        content.append(_make_trailing_se())
    else:
        last = content[-1]
        if last.paragraph is not None:
            elems = last.paragraph.elements or []
            if not (
                len(elems) == 1
                and elems[0].text_run is not None
                and elems[0].text_run.content == "\n"
                and elems[0].text_run.text_style is None
            ):
                content.append(_make_trailing_se())
        else:
            content.append(_make_trailing_se())

    style_d: dict[str, Any] = {}
    if bg_hex:
        opt_color = hex_to_optional_color(bg_hex)
        style_d["backgroundColor"] = opt_color.model_dump(by_alias=True, exclude_none=True)
    if border_left:
        border = str_to_cell_border(border_left)
        if border:
            style_d["borderLeft"] = border.model_dump(by_alias=True, exclude_none=True)
            # Zero-width transparent borders on other sides (so only left shows)
            # dashStyle must be a valid value — SOLID is the safest choice.
            zero = {
                "width": {"magnitude": 0, "unit": "PT"},
                "color": {"color": {}},
                "dashStyle": "SOLID",
            }
            style_d.setdefault("borderTop", zero)
            style_d.setdefault("borderRight", zero)
            style_d.setdefault("borderBottom", zero)

    cell_style = TableCellStyle.model_validate(style_d) if style_d else TableCellStyle()
    cell = TableCell(content=content, table_cell_style=cell_style)
    row = TableRow(table_cells=[cell])
    return Table(rows=1, columns=1, table_rows=[row])


def _extract_cell_text_lines(table: Table) -> list[str]:
    """Extract text lines from the first cell of a 1×1 table.

    Each paragraph becomes one line, including blank-line paragraphs inside
    code blocks (empty string → blank line in the fenced block).  Only
    trailing empty lines are stripped — they come from the mandatory trailing
    paragraph that every table cell must end with, which the real API may
    leave with an inherited style that prevents the usual content == "\\n"
    check from firing.

    Preserving internal blank-line paragraphs is critical for index accuracy:
    the real API stores them as actual paragraphs, so the deserialized base
    document must match the real document's paragraph count or reconciler
    deleteContentRange ranges will be off.
    """
    rows = table.table_rows or []
    if not rows:
        return []
    cells = rows[0].table_cells or []
    if not cells:
        return []
    cell = cells[0]
    lines: list[str] = []
    for se in cell.content or []:
        if se.paragraph is None:
            continue
        elems = se.paragraph.elements or []
        # Collect text (strip trailing \n from each run)
        line_parts: list[str] = []
        for pe in elems:
            if pe.text_run and pe.text_run.content:
                line_parts.append(pe.text_run.content.rstrip("\n"))
        lines.append("".join(line_parts))
    # Strip trailing empty lines — these come from the mandatory trailing
    # paragraph (with or without inherited style).  Internal blank lines
    # (e.g. between code sections) are intentionally preserved above.
    while lines and not lines[-1]:
        lines.pop()
    return lines


# Monospace font style for code content
def _code_text_style() -> TextStyle:
    return TextStyle.model_validate(
        {
            "weightedFontFamily": {"fontFamily": "Courier New"},
            "fontSize": {"magnitude": 10, "unit": "PT"},
        }
    )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class SpecialElement(ABC):
    """A markdown element that maps to a named-range-annotated 1×1 Table."""

    @property
    @abstractmethod
    def named_range_name(self) -> str:
        """Named range name: extradoc:<type>[:<variant>]."""

    @abstractmethod
    def to_table(self) -> Table:
        """Build a 1×1 Google Docs Table with canonical content and visual styling."""

    @abstractmethod
    def to_markdown(self) -> str:
        """Render as a markdown string (no trailing newline)."""

    @classmethod
    @abstractmethod
    def from_table(cls, table: Table, named_range_name: str) -> "SpecialElement":
        """Reconstruct from a named-range-annotated table on pull."""


# ---------------------------------------------------------------------------
# CodeBlock
# ---------------------------------------------------------------------------


@dataclass
class CodeBlock(SpecialElement):
    """A fenced code block: ```lang\\ncode\\n```."""

    language: str = ""          # e.g. "python", "" for language-less
    lines: list[str] = field(default_factory=list)

    @property
    def named_range_name(self) -> str:
        if self.language:
            return f"extradoc:codeblock:{self.language}"
        return "extradoc:codeblock"

    def to_markdown(self) -> str:
        fence = f"```{self.language}" if self.language else "```"
        return fence + "\n" + "\n".join(self.lines) + "\n```"

    def to_table(self) -> Table:
        ts = _code_text_style()
        paragraphs = [_build_para(line, ts) for line in self.lines]
        return _make_1x1_table(paragraphs, bg_hex="#f3f3f3")

    @classmethod
    def from_table(cls, table: Table, named_range_name: str) -> "CodeBlock":
        parts = named_range_name.split(":")
        language = parts[2] if len(parts) > 2 else ""
        lines = _extract_cell_text_lines(table)
        return cls(language=language, lines=lines)


# ---------------------------------------------------------------------------
# Callout
# ---------------------------------------------------------------------------


@dataclass
class Callout(SpecialElement):
    """A GitHub-style callout: > [!WARNING]\\n> text."""

    variant: Literal["warning", "info", "note", "danger", "tip"] = "info"
    lines: list[str] = field(default_factory=list)

    _BG: ClassVar[dict[str, str]] = {
        "warning": "#fff3cd",
        "info":    "#d1ecf1",
        "note":    "#d1ecf1",  # same as info
        "danger":  "#f8d7da",
        "tip":     "#d4edda",
    }

    @property
    def named_range_name(self) -> str:
        return f"extradoc:callout:{self.variant}"

    def to_markdown(self) -> str:
        header = f"> [!{self.variant.upper()}]"
        body = [f"> {line}" for line in self.lines]
        return "\n".join([header] + body)

    def to_table(self) -> Table:
        bg = self._BG.get(self.variant, "#d1ecf1")
        paragraphs = [_build_para(line) for line in self.lines]
        return _make_1x1_table(paragraphs, bg_hex=bg)

    @classmethod
    def from_table(cls, table: Table, named_range_name: str) -> "Callout":
        parts = named_range_name.split(":")
        raw_variant = parts[2] if len(parts) > 2 else "info"
        variant: Literal["warning", "info", "note", "danger", "tip"] = (
            raw_variant if raw_variant in ("warning", "info", "note", "danger", "tip") else "info"
        )
        lines = _extract_cell_text_lines(table)
        return cls(variant=variant, lines=lines)


# ---------------------------------------------------------------------------
# Blockquote
# ---------------------------------------------------------------------------


@dataclass
class Blockquote(SpecialElement):
    """A plain block quotation: > text."""

    lines: list[str] = field(default_factory=list)

    @property
    def named_range_name(self) -> str:
        return "extradoc:blockquote"

    def to_markdown(self) -> str:
        return "\n".join(f"> {line}" for line in self.lines)

    def to_table(self) -> Table:
        paragraphs = [_build_para(line) for line in self.lines]
        return _make_1x1_table(
            paragraphs, bg_hex="#f9f9f9", border_left="3.0,#888888,SOLID"
        )

    @classmethod
    def from_table(cls, table: Table, named_range_name: str) -> "Blockquote":
        lines = _extract_cell_text_lines(table)
        return cls(lines=lines)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def special_element_from_named_range(
    table: Table, named_range_name: str
) -> SpecialElement:
    """Construct the typed element given a table and its extradoc:* named range name.

    Raises:
        ValueError: if the named_range_name is not a recognised extradoc type.
    """
    parts = named_range_name.split(":")
    if len(parts) < 2 or parts[0] != "extradoc":
        raise ValueError(f"Not an extradoc named range: {named_range_name!r}")
    type_ = parts[1]
    if type_ == "codeblock":
        return CodeBlock.from_table(table, named_range_name)
    if type_ == "callout":
        return Callout.from_table(table, named_range_name)
    if type_ == "blockquote":
        return Blockquote.from_table(table, named_range_name)
    raise ValueError(f"Unknown extradoc element type: {named_range_name!r}")
