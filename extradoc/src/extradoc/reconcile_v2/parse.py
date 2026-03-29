"""Parse transport ``Document`` values into canonical semantic IR.

This is a confidence-sprint parser. It intentionally covers only enough of the
surface to validate the top-down model against real transport payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from extradoc.indexer import utf16_len
from extradoc.reconcile_v2.errors import ParseIRError, UnsupportedSpikeError
from extradoc.reconcile_v2.ir import (
    BODY_CAPABILITIES,
    FOOTER_CAPABILITIES,
    FOOTNOTE_CAPABILITIES,
    HEADER_CAPABILITIES,
    TABLE_CELL_CAPABILITIES,
    AnchorRangeIR,
    AnnotationCatalogIR,
    AutoTextIR,
    BodyStoryIR,
    CellIR,
    DocumentIR,
    FlowPathIR,
    FootnoteRefIR,
    InlineIR,
    InlineObjectRefIR,
    ListIR,
    ListItemIR,
    ListLevelSpecIR,
    ListSpecIR,
    OpaqueBlockIR,
    OpaqueInlineIR,
    PageBreakIR,
    ParagraphIR,
    PositionEdge,
    PositionIR,
    ResourceGraphIR,
    RowIR,
    SectionAttachmentsIR,
    SectionIR,
    StoryIR,
    StoryKind,
    StyleEnvironmentIR,
    StylePayload,
    TabIR,
    TableIR,
    TextSpanIR,
    TocIR,
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Document,
        DocumentStyle,
        DocumentTab,
        NamedRange,
        NamedRanges,
        Paragraph,
        ParagraphElement,
        SectionStyle,
        StructuralElement,
        Tab,
        TextRun,
    )

HEADER_SLOT_FIELDS = {
    "DEFAULT": "default_header_id",
    "FIRST_PAGE": "first_page_header_id",
    "EVEN_PAGE": "even_page_header_id",
}
FOOTER_SLOT_FIELDS = {
    "DEFAULT": "default_footer_id",
    "FIRST_PAGE": "first_page_footer_id",
    "EVEN_PAGE": "even_page_footer_id",
}


@dataclass(slots=True)
class _InlineSpan:
    inline_index: int
    start: int
    end: int


@dataclass(slots=True)
class _ParagraphResolver:
    section_index: int | None
    block_index: int
    node_path: tuple[int, ...]
    start: int
    end: int
    spans: list[_InlineSpan]


@dataclass(slots=True)
class _BlockBoundary:
    section_index: int | None
    block_index: int
    start: int
    end: int
    kind: str


@dataclass(slots=True)
class _StoryResolver:
    story_id: str
    paragraphs: list[_ParagraphResolver] = field(default_factory=list)
    block_boundaries: list[_BlockBoundary] = field(default_factory=list)

    def add_block(
        self,
        *,
        section_index: int | None,
        block_index: int,
        start: int,
        end: int,
        kind: str = "other",
    ) -> None:
        self.block_boundaries.append(
            _BlockBoundary(
                section_index=section_index,
                block_index=block_index,
                start=start,
                end=end,
                kind=kind,
            )
        )

    def add_paragraph(
        self,
        *,
        section_index: int | None,
        block_index: int,
        node_path: tuple[int, ...],
        start: int,
        end: int,
        spans: list[_InlineSpan],
    ) -> None:
        self.paragraphs.append(
            _ParagraphResolver(
                section_index=section_index,
                block_index=block_index,
                node_path=node_path,
                start=start,
                end=end,
                spans=spans,
            )
        )

    def resolve(self, index: int, *, is_end: bool) -> PositionIR:
        for para in self.paragraphs:
            for span in para.spans:
                if span.start <= index < span.end:
                    return PositionIR(
                        story_id=self.story_id,
                        path=FlowPathIR(
                            section_index=para.section_index,
                            block_index=para.block_index,
                            node_path=para.node_path,
                            inline_index=span.inline_index,
                            text_offset_utf16=index - span.start,
                            edge=PositionEdge.INTERIOR,
                        ),
                    )
                if is_end and index == span.end:
                    return PositionIR(
                        story_id=self.story_id,
                        path=FlowPathIR(
                            section_index=para.section_index,
                            block_index=para.block_index,
                            node_path=para.node_path,
                            inline_index=span.inline_index,
                            text_offset_utf16=span.end - span.start,
                            edge=PositionEdge.INTERIOR,
                        ),
                    )
            if index == para.start:
                return PositionIR(
                    story_id=self.story_id,
                    path=FlowPathIR(
                        section_index=para.section_index,
                        block_index=para.block_index,
                        node_path=para.node_path,
                        edge=PositionEdge.BEFORE,
                    ),
                )
            if is_end and index == para.end:
                return PositionIR(
                    story_id=self.story_id,
                    path=FlowPathIR(
                        section_index=para.section_index,
                        block_index=para.block_index,
                        node_path=para.node_path,
                        edge=PositionEdge.AFTER,
                    ),
                )

        for block in self.block_boundaries:
            if index == block.start:
                return PositionIR(
                    story_id=self.story_id,
                    path=FlowPathIR(
                        section_index=block.section_index,
                        block_index=block.block_index,
                        edge=PositionEdge.BEFORE,
                    ),
                )
            if is_end and index == block.end:
                return PositionIR(
                    story_id=self.story_id,
                    path=FlowPathIR(
                        section_index=block.section_index,
                        block_index=block.block_index,
                        edge=PositionEdge.AFTER,
                    ),
                )
            if block.kind == "table" and block.start < index < block.end:
                return PositionIR(
                    story_id=self.story_id,
                    path=FlowPathIR(
                        section_index=block.section_index,
                        block_index=block.block_index,
                        edge=PositionEdge.BEFORE,
                    ),
                )

        raise UnsupportedSpikeError(
            f"Cannot resolve transport index {index} in story {self.story_id}. "
            "The confidence-sprint parser currently supports anchors in paragraph "
            "text and at block boundaries only."
        )


def parse_document(document: Document) -> DocumentIR:
    """Parse a transport document into the spike semantic IR."""
    return DocumentIR(
        revision_id=document.revision_id,
        tabs=[
            _parse_tab(tab, parent_tab_id=None, tab_ordinal=i)
            for i, tab in enumerate(document.tabs or [])
        ],
    )


def _parse_tab(tab: Tab, *, parent_tab_id: str | None, tab_ordinal: int) -> TabIR:
    props = tab.tab_properties
    tab_id = props.tab_id if props and props.tab_id else f"tab-{tab_ordinal}"
    document_tab = tab.document_tab
    style_env = _parse_style_env(document_tab)

    resolvers: dict[str, _StoryResolver] = {}
    body, body_resolver = _parse_body_story(
        tab_id=tab_id,
        document_tab=document_tab,
        style_env=style_env,
    )
    resolvers[""] = body_resolver

    resource_graph = ResourceGraphIR(
        headers=_parse_story_catalog(
            tab_id=tab_id,
            story_kind=StoryKind.HEADER,
            story_map=(document_tab.headers if document_tab else None) or {},
            style_env=style_env,
            resolvers=resolvers,
        ),
        footers=_parse_story_catalog(
            tab_id=tab_id,
            story_kind=StoryKind.FOOTER,
            story_map=(document_tab.footers if document_tab else None) or {},
            style_env=style_env,
            resolvers=resolvers,
        ),
        footnotes=_parse_story_catalog(
            tab_id=tab_id,
            story_kind=StoryKind.FOOTNOTE,
            story_map=(document_tab.footnotes if document_tab else None) or {},
            style_env=style_env,
            resolvers=resolvers,
        ),
        inline_objects={
            key: _as_dict(value)
            for key, value in (
                (document_tab.inline_objects if document_tab else None) or {}
            ).items()
        },
        positioned_objects={
            key: _as_dict(value)
            for key, value in (
                (document_tab.positioned_objects if document_tab else None) or {}
            ).items()
        },
    )

    annotations = _parse_annotations(
        tab_id=tab_id,
        named_ranges=(document_tab.named_ranges if document_tab else None) or {},
        resolvers=resolvers,
    )

    child_tabs = [
        _parse_tab(child, parent_tab_id=tab_id, tab_ordinal=i)
        for i, child in enumerate(tab.child_tabs or [])
    ]
    return TabIR(
        id=tab_id,
        parent_tab_id=(
            props.parent_tab_id if props and props.parent_tab_id else parent_tab_id
        ),
        title=props.title if props and props.title else "",
        index=props.index if props and props.index is not None else tab_ordinal,
        icon_emoji=props.icon_emoji if props else None,
        style_env=style_env,
        body=body,
        resource_graph=resource_graph,
        annotations=annotations,
        child_tabs=child_tabs,
    )


def _parse_style_env(document_tab: DocumentTab | None) -> StyleEnvironmentIR:
    if document_tab is None:
        return StyleEnvironmentIR(document_style={}, named_styles={}, list_catalog={})
    return StyleEnvironmentIR(
        document_style=_as_dict(document_tab.document_style),
        named_styles=_as_dict(document_tab.named_styles),
        list_catalog={
            key: _as_dict(value)
            for key, value in (document_tab.lists or {}).items()
        },
    )


def _parse_body_story(
    *,
    tab_id: str,
    document_tab: DocumentTab | None,
    style_env: StyleEnvironmentIR,
) -> tuple[BodyStoryIR, _StoryResolver]:
    body_story_id = f"{tab_id}:body"
    body_resolver = _StoryResolver(story_id=body_story_id)
    content = (
        document_tab.body.content
        if document_tab and document_tab.body and document_tab.body.content
        else []
    )
    document_style = document_tab.document_style if document_tab else None

    sections: list[SectionIR] = []
    current_elements: list[StructuralElement] = []
    current_section_style: SectionStyle | None = None
    section_ordinal = 0

    for element in content:
        if element.section_break is not None:
            if current_section_style is not None:
                section = _build_section(
                    tab_id=tab_id,
                    body_story_id=body_story_id,
                    section_ordinal=section_ordinal,
                    section_style=current_section_style,
                    document_style=document_style,
                    elements=current_elements,
                    style_env=style_env,
                    resolver=body_resolver,
                )
                sections.append(section)
                section_ordinal += 1
                current_elements = []
            current_section_style = element.section_break.section_style
        else:
            current_elements.append(element)

    if current_section_style is None:
        current_section_style = None

    section = _build_section(
        tab_id=tab_id,
        body_story_id=body_story_id,
        section_ordinal=section_ordinal,
        section_style=current_section_style,
        document_style=document_style,
        elements=current_elements,
        style_env=style_env,
        resolver=body_resolver,
    )
    sections.append(section)

    return (
        BodyStoryIR(id=body_story_id, kind=StoryKind.BODY, sections=sections),
        body_resolver,
    )


def _build_section(
    *,
    tab_id: str,
    body_story_id: str,
    section_ordinal: int,
    section_style: SectionStyle | None,
    document_style: DocumentStyle | None,
    elements: list[StructuralElement],
    style_env: StyleEnvironmentIR,
    resolver: _StoryResolver,
) -> SectionIR:
    blocks = _parse_story_blocks(
        elements=elements,
        story_id=body_story_id,
        section_index=section_ordinal,
        style_env=style_env,
        resolver=resolver,
    )
    return SectionIR(
        id=f"{tab_id}:section:{section_ordinal}",
        style=_as_dict(section_style),
        attachments=_resolve_section_attachments(section_style, document_style),
        blocks=blocks,
    )


def _parse_story_catalog(
    *,
    tab_id: str,
    story_kind: StoryKind,
    story_map: dict[str, Any],
    style_env: StyleEnvironmentIR,
    resolvers: dict[str, _StoryResolver],
) -> dict[str, StoryIR]:
    result: dict[str, StoryIR] = {}
    for story_ref, transport_story in story_map.items():
        story_id = f"{tab_id}:{story_kind.value.lower()}:{story_ref}"
        resolver = _StoryResolver(story_id=story_id)
        blocks = _parse_story_blocks(
            elements=transport_story.content or [],
            story_id=story_id,
            section_index=None,
            style_env=style_env,
            resolver=resolver,
        )
        result[story_ref] = StoryIR(
            id=story_id,
            kind=story_kind,
            capabilities=_capabilities_for_story_kind(story_kind),
            blocks=blocks,
        )
        resolvers[story_ref] = resolver
    return result


def _parse_story_blocks(
    *,
    elements: list[StructuralElement],
    story_id: str,
    section_index: int | None,
    style_env: StyleEnvironmentIR,
    resolver: _StoryResolver,
) -> list[Any]:
    blocks: list[Any] = []
    i = 0
    while i < len(elements):
        element = elements[i]
        block_index = len(blocks)

        if (
            element.paragraph is not None
            and element.paragraph.bullet
            and element.paragraph.bullet.list_id
        ):
            list_id = element.paragraph.bullet.list_id
            list_elements: list[StructuralElement] = []
            while i < len(elements):
                candidate = elements[i]
                bullet = candidate.paragraph.bullet if candidate.paragraph else None
                if (
                    candidate.paragraph is None
                    or bullet is None
                    or bullet.list_id != list_id
                ):
                    break
                list_elements.append(candidate)
                i += 1

            items: list[ListItemIR] = []
            for item_index, list_element in enumerate(list_elements):
                para_ir, spans, start, end = _parse_paragraph(list_element.paragraph)
                items.append(
                    ListItemIR(
                        level=list_element.paragraph.bullet.nesting_level or 0,
                        paragraph=para_ir,
                    )
                )
                resolver.add_paragraph(
                    section_index=section_index,
                    block_index=block_index,
                    node_path=(item_index,),
                    start=start,
                    end=end,
                    spans=spans,
                )
            resolver.add_block(
                section_index=section_index,
                block_index=block_index,
                start=list_elements[0].start_index or 0,
                end=list_elements[-1].end_index or list_elements[0].start_index or 0,
            )
            blocks.append(
                ListIR(
                    spec=_parse_list_spec(list_id, style_env.list_catalog),
                    items=items,
                )
            )
            continue

        if element.paragraph is not None:
            para = element.paragraph
            if _is_page_break_paragraph(para):
                resolver.add_block(
                    section_index=section_index,
                    block_index=block_index,
                    start=element.start_index or 0,
                    end=element.end_index or element.start_index or 0,
                    kind="page_break",
                )
                blocks.append(PageBreakIR())
            else:
                para_ir, spans, start, end = _parse_paragraph(para)
                resolver.add_block(
                    section_index=section_index,
                    block_index=block_index,
                    start=element.start_index or start,
                    end=element.end_index or end,
                    kind="paragraph",
                )
                resolver.add_paragraph(
                    section_index=section_index,
                    block_index=block_index,
                    node_path=(),
                    start=start,
                    end=end,
                    spans=spans,
                )
                blocks.append(para_ir)
            i += 1
            continue

        if element.table is not None:
            resolver.add_block(
                section_index=section_index,
                block_index=block_index,
                start=element.start_index or 0,
                end=element.end_index or element.start_index or 0,
                kind="table",
            )
            blocks.append(
                _parse_table(
                    element.table,
                    story_id=story_id,
                    block_index=block_index,
                    style_env=style_env,
                )
            )
            i += 1
            continue

        if element.table_of_contents is not None:
            resolver.add_block(
                section_index=section_index,
                block_index=block_index,
                start=element.start_index or 0,
                end=element.end_index or element.start_index or 0,
                kind="toc",
            )
            blocks.append(TocIR(style={}))
            i += 1
            continue

        if element.section_break is not None:
            raise ParseIRError("Section breaks should be handled at body partition time.")

        resolver.add_block(
            section_index=section_index,
            block_index=block_index,
            start=element.start_index or 0,
            end=element.end_index or element.start_index or 0,
            kind="opaque",
        )
        blocks.append(OpaqueBlockIR(kind="unknown", payload=_as_dict(element)))
        i += 1

    return blocks


def _parse_table(
    table: Any,
    *,
    story_id: str,
    block_index: int,
    style_env: StyleEnvironmentIR,
) -> TableIR:
    rows: list[RowIR] = []
    derived_pinned_header_rows = 0
    for row_index, row in enumerate(table.table_rows or []):
        cells: list[CellIR] = []
        for col_index, cell in enumerate(row.table_cells or []):
            cell_story_id = f"{story_id}:table:{block_index}:r{row_index}:c{col_index}"
            cell_resolver = _StoryResolver(story_id=cell_story_id)
            cell_blocks = _parse_story_blocks(
                elements=cell.content or [],
                story_id=cell_story_id,
                section_index=None,
                style_env=style_env,
                resolver=cell_resolver,
            )
            cell_story = StoryIR(
                id=cell_story_id,
                kind=StoryKind.TABLE_CELL,
                capabilities=TABLE_CELL_CAPABILITIES,
                blocks=cell_blocks,
            )
            style = _as_dict(cell.table_cell_style)
            cells.append(
                CellIR(
                    style=style,
                    row_span=style.get("rowSpan") or 1,
                    column_span=style.get("columnSpan") or 1,
                    merge_head=None,
                    content=cell_story,
                )
            )
        row_style = _as_dict(row.table_row_style)
        if row_style.get("tableHeader") and row_index == derived_pinned_header_rows:
            derived_pinned_header_rows += 1
        row_style.pop("tableHeader", None)
        rows.append(RowIR(style=row_style, cells=cells))

    table_payload = _as_dict(table)
    table_style = _as_dict(table.table_style)
    return TableIR(
        style=table_style,
        pinned_header_rows=table_payload.get("pinnedHeaderRowsCount")
        or derived_pinned_header_rows,
        column_properties=list(table_style.get("tableColumnProperties", [])),
        merge_regions=[],
        rows=rows,
    )


def _parse_paragraph(
    paragraph: Paragraph,
) -> tuple[ParagraphIR, list[_InlineSpan], int, int]:
    role = (
        _enum_value(getattr(paragraph.paragraph_style, "named_style_type", None))
        or "NORMAL_TEXT"
    )
    explicit_style = _as_dict(paragraph.paragraph_style)
    inlines: list[InlineIR] = []
    spans: list[_InlineSpan] = []

    para_start = None
    para_end = None
    for element in paragraph.elements or []:
        if para_start is None and element.start_index is not None:
            para_start = element.start_index
        if element.end_index is not None:
            para_end = element.end_index

        inline, span = _parse_inline(element, inline_index=len(inlines))
        if inline is not None:
            inlines.append(inline)
        if span is not None:
            spans.append(span)

    if para_start is None:
        para_start = 0
    if para_end is None:
        para_end = para_start
    if spans:
        para_end = spans[-1].end
    return ParagraphIR(role=role, explicit_style=explicit_style, inlines=inlines), spans, para_start, para_end


def _parse_inline(
    element: ParagraphElement, *, inline_index: int
) -> tuple[InlineIR | None, _InlineSpan | None]:
    start = element.start_index or 0
    end = element.end_index or start

    if element.text_run is not None:
        return _parse_text_run(
            element.text_run,
            inline_index=inline_index,
            start=start,
        )

    if element.footnote_reference is not None:
        return FootnoteRefIR(ref=element.footnote_reference.footnote_id or ""), _InlineSpan(
            inline_index=inline_index,
            start=start,
            end=end,
        )

    if element.inline_object_element is not None:
        return InlineObjectRefIR(
            ref=element.inline_object_element.inline_object_id or ""
        ), _InlineSpan(inline_index=inline_index, start=start, end=end)

    if element.auto_text is not None:
        return AutoTextIR(
            kind=_enum_value(element.auto_text.type) or "AUTO_TEXT",
            payload=_as_dict(element.auto_text),
        ), _InlineSpan(inline_index=inline_index, start=start, end=end)

    if element.page_break is not None:
        return None, None

    for kind in (
        "person",
        "date_element",
        "rich_link",
        "horizontal_rule",
        "equation",
        "column_break",
    ):
        value = getattr(element, kind, None)
        if value is not None:
            return OpaqueInlineIR(kind=kind, payload=_as_dict(value)), _InlineSpan(
                inline_index=inline_index,
                start=start,
                end=end,
            )

    return None, None


def _parse_text_run(
    text_run: TextRun,
    *,
    inline_index: int,
    start: int,
) -> tuple[InlineIR | None, _InlineSpan | None]:
    content = text_run.content or ""
    visible = content[:-1] if content.endswith("\n") else content
    if not visible:
        return None, None
    visible_end = start + utf16_len(visible)
    return TextSpanIR(
        text=visible,
        explicit_text_style=_as_dict(text_run.text_style),
    ), _InlineSpan(inline_index=inline_index, start=start, end=visible_end)


def _parse_list_spec(list_id: str, list_catalog: dict[str, StylePayload]) -> ListSpecIR:
    raw = list_catalog.get(list_id, {})
    list_props = raw.get("listProperties", {}) if isinstance(raw, dict) else {}
    nesting_levels = (
        list_props.get("nestingLevels", []) if isinstance(list_props, dict) else []
    )

    levels: list[ListLevelSpecIR] = []
    signature_parts: list[str] = []
    for level in nesting_levels:
        glyph_kind = (
            _enum_value(level.get("glyphType")) if isinstance(level, dict) else None
        )
        glyph_symbol = level.get("glyphSymbol") if isinstance(level, dict) else None
        start_number = level.get("startNumber") if isinstance(level, dict) else None
        levels.append(
            ListLevelSpecIR(
                glyph_kind=glyph_kind,
                glyph_symbol=glyph_symbol,
                start_number=start_number,
                indent_start=(
                    level.get("indentStart") if isinstance(level, dict) else None
                ),
                indent_first_line=(
                    level.get("indentFirstLine") if isinstance(level, dict) else None
                ),
                text_style=level.get("textStyle", {}) if isinstance(level, dict) else {},
            )
        )
        signature_parts.append(f"{glyph_kind}:{glyph_symbol}:{start_number}")

    if any("CHECKBOX" in part for part in signature_parts):
        kind = "CHECKBOX"
    elif any("DECIMAL" in part or "ROMAN" in part for part in signature_parts):
        kind = "NUMBERED"
    else:
        kind = "BULLETED"
    signature = "|".join(signature_parts) if signature_parts else f"transport:{list_id}"
    return ListSpecIR(signature=signature, kind=kind, levels=levels)


def _resolve_section_attachments(
    section_style: SectionStyle | None,
    document_style: DocumentStyle | None,
) -> SectionAttachmentsIR:
    return SectionAttachmentsIR(
        headers=_resolve_slot_map(section_style, document_style, HEADER_SLOT_FIELDS),
        footers=_resolve_slot_map(section_style, document_style, FOOTER_SLOT_FIELDS),
    )


def _resolve_slot_map(
    section_style: SectionStyle | None,
    document_style: DocumentStyle | None,
    fields: dict[str, str],
) -> dict[str, str]:
    slots: dict[str, str] = {}
    for slot, field_name in fields.items():
        section_value = (
            getattr(section_style, field_name, None) if section_style else None
        )
        document_value = (
            getattr(document_style, field_name, None) if document_style else None
        )
        value = section_value or document_value
        if value:
            slots[slot] = value
    return slots


def _parse_annotations(
    *,
    tab_id: str,
    named_ranges: dict[str, NamedRanges],
    resolvers: dict[str, _StoryResolver],
) -> AnnotationCatalogIR:
    annotations: dict[str, list[AnchorRangeIR]] = {}
    for name, grouped in named_ranges.items():
        ranges: list[AnchorRangeIR] = []
        for named_range in grouped.named_ranges or []:
            ranges.extend(
                _parse_named_range(
                    tab_id=tab_id,
                    name=name,
                    named_range=named_range,
                    resolvers=resolvers,
                )
            )
        annotations[name] = ranges
    return AnnotationCatalogIR(named_ranges=annotations)


def _parse_named_range(
    *,
    tab_id: str,
    name: str,
    named_range: NamedRange,
    resolvers: dict[str, _StoryResolver],
) -> list[AnchorRangeIR]:
    anchors: list[AnchorRangeIR] = []
    for range_ in named_range.ranges or []:
        if range_.tab_id and str(range_.tab_id) != tab_id:
            continue
        segment_id = str(range_.segment_id) if range_.segment_id else ""
        resolver = resolvers.get(segment_id)
        if resolver is None:
            raise ParseIRError(
                f"No resolver found for named range segment {segment_id!r} in tab {tab_id}."
            )
        if range_.start_index is None or range_.end_index is None:
            raise ParseIRError(f"Named range {name!r} is missing start/end indices.")
        anchors.append(
            AnchorRangeIR(
                name=name,
                start=resolver.resolve(range_.start_index, is_end=False),
                end=resolver.resolve(range_.end_index, is_end=True),
            )
        )
    return anchors


def _is_page_break_paragraph(paragraph: Paragraph) -> bool:
    saw_page_break = False
    for element in paragraph.elements or []:
        if element.page_break is not None:
            saw_page_break = True
            continue
        text_run = element.text_run
        if text_run is not None and (text_run.content or "") == "\n":
            continue
        return False
    return saw_page_break


def _capabilities_for_story_kind(kind: StoryKind) -> Any:
    if kind == StoryKind.HEADER:
        return HEADER_CAPABILITIES
    if kind == StoryKind.FOOTER:
        return FOOTER_CAPABILITIES
    if kind == StoryKind.FOOTNOTE:
        return FOOTNOTE_CAPABILITIES
    if kind == StoryKind.TABLE_CELL:
        return TABLE_CELL_CAPABILITIES
    return BODY_CAPABILITIES


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _as_dict(model: Any) -> StylePayload:
    if model is None:
        return {}
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump(by_alias=True, exclude_none=True, mode="json")
    return dict(model)
