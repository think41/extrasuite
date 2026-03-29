"""Shared testing helpers for semantic IR and plan normalization."""

from __future__ import annotations

from collections import Counter

from extradoc.reconcile_v2.ir import (
    BodyStoryIR,
    DocumentIR,
    ListIR,
    OpaqueBlockIR,
    PageBreakIR,
    ParagraphIR,
    TabIR,
    TableIR,
    TocIR,
)


def summarize_document_ir(document: DocumentIR) -> str:
    """Return a compact human-readable summary of the semantic IR."""
    lines = [f"revision={document.revision_id or '<none>'}", f"tabs={len(document.tabs)}"]
    for tab in document.tabs:
        lines.extend(_summarize_tab(tab))
    return "\n".join(lines)


def _summarize_tab(tab: TabIR) -> list[str]:
    lines = [
        f"tab {tab.id!r} title={tab.title!r} index={tab.index} children={len(tab.child_tabs)}",
        f"  body sections={len(tab.body.sections)} blocks={_count_body_blocks(tab.body)}",
        (
            "  resources "
            f"headers={len(tab.resource_graph.headers)} "
            f"footers={len(tab.resource_graph.footers)} "
            f"footnotes={len(tab.resource_graph.footnotes)}"
        ),
        f"  named_ranges={sum(len(v) for v in tab.annotations.named_ranges.values())}",
    ]
    counts = _block_counts_for_body(tab.body)
    if counts:
        lines.append(f"  body block kinds={dict(counts)}")
    return lines


def _count_body_blocks(body: BodyStoryIR) -> int:
    return sum(len(section.blocks) for section in body.sections)


def _block_counts_for_body(body: BodyStoryIR) -> Counter[str]:
    counts: Counter[str] = Counter()
    for section in body.sections:
        counts.update(_block_counts(section.blocks))
    return counts


def _block_counts(blocks: list[object]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for block in blocks:
        if isinstance(block, ParagraphIR):
            counts["paragraph"] += 1
        elif isinstance(block, ListIR):
            counts["list"] += 1
        elif isinstance(block, TableIR):
            counts["table"] += 1
        elif isinstance(block, PageBreakIR):
            counts["page_break"] += 1
        elif isinstance(block, TocIR):
            counts["toc"] += 1
        elif isinstance(block, OpaqueBlockIR):
            counts[f"opaque:{block.kind}"] += 1
    return counts
