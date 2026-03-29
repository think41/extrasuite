"""Utilities for comparing authored markdown against pulled markdown structurally."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.diff import diff_documents, summarize_semantic_edits
from extradoc.serde._from_markdown import markdown_to_document

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class MarkdownComparison:
    matching: bool
    missing_tabs: tuple[str, ...]
    extra_tabs: tuple[str, ...]
    semantic_edits: tuple[str, ...]
    tab_diffs: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, object]:
        return {
            "matching": self.matching,
            "missing_tabs": list(self.missing_tabs),
            "extra_tabs": list(self.extra_tabs),
            "semantic_edits": list(self.semantic_edits),
            "tab_diffs": {name: list(lines) for name, lines in self.tab_diffs.items()},
        }


def load_markdown_tabs(folder: Path) -> dict[str, str]:
    """Load per-tab markdown content from a pull-md folder."""
    tabs: dict[str, str] = {}
    for path in sorted(folder.glob("*.md")):
        if path.name == "index.md":
            continue
        tabs[path.stem] = path.read_text(encoding="utf-8")
    return tabs


def compare_markdown_tabs(
    desired_tabs: dict[str, str],
    actual_tabs: dict[str, str],
) -> MarkdownComparison:
    """Compare two per-tab markdown mappings semantically and textually."""
    desired_names = set(desired_tabs)
    actual_names = set(actual_tabs)
    missing_tabs = tuple(sorted(desired_names - actual_names))
    extra_tabs = tuple(sorted(actual_names - desired_names))

    tab_diffs: dict[str, tuple[str, ...]] = {}
    for name in sorted(desired_names & actual_names):
        if desired_tabs[name] == actual_tabs[name]:
            continue
        diff_lines = tuple(
            difflib.unified_diff(
                desired_tabs[name].splitlines(),
                actual_tabs[name].splitlines(),
                fromfile=f"desired/{name}.md",
                tofile=f"actual/{name}.md",
                lineterm="",
            )
        )
        if diff_lines:
            tab_diffs[name] = diff_lines

    semantic_edits: tuple[str, ...] = ()
    if not missing_tabs and not extra_tabs:
        tab_ids = {
            name: f"t.{index}"
            for index, name in enumerate(sorted(desired_tabs))
        }
        normalized_desired_tabs = {
            name: _normalize_markdown_for_semantic_compare(desired_tabs[name])
            for name in sorted(desired_tabs)
        }
        normalized_actual_tabs = {
            name: _normalize_markdown_for_semantic_compare(actual_tabs[name])
            for name in sorted(actual_tabs)
        }
        desired_doc = reindex_document(
            markdown_to_document(
                normalized_desired_tabs,
                document_id="markdown-compare",
                title="Markdown Compare",
                tab_ids=tab_ids,
            )
        )
        actual_doc = reindex_document(
            markdown_to_document(
                normalized_actual_tabs,
                document_id="markdown-compare",
                title="Markdown Compare",
                tab_ids=tab_ids,
            )
        )
        semantic_edits = tuple(summarize_semantic_edits(diff_documents(actual_doc, desired_doc)))

    return MarkdownComparison(
        matching=not missing_tabs and not extra_tabs and not semantic_edits,
        missing_tabs=missing_tabs,
        extra_tabs=extra_tabs,
        semantic_edits=semantic_edits,
        tab_diffs=tab_diffs,
    )


_FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\]")
_FOOTNOTE_DEF_RE = re.compile(r"(?m)^\[\^([^\]]+)\]:")


def _normalize_markdown_for_semantic_compare(text: str) -> str:
    label_map: dict[str, str] = {}

    def canonical_label(label: str) -> str:
        existing = label_map.get(label)
        if existing is not None:
            return existing
        canonical = f"fn{len(label_map) + 1}"
        label_map[label] = canonical
        return canonical

    text = _FOOTNOTE_DEF_RE.sub(lambda m: f"[^{canonical_label(m.group(1))}]:", text)
    text = _FOOTNOTE_REF_RE.sub(lambda m: f"[^{canonical_label(m.group(1))}]", text)
    return text
