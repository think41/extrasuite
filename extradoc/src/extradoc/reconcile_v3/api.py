"""Public interface for reconcile_v3.

reconcile_v3 is the active top-down tree-oriented Google Docs reconciler.

- Works directly with typed ``Document`` models (no raw dict step).
- Top-down traversal with stable-ID matching at every tree level.
- Lowering produces one or more request batches; later batches use
  deferred-ID placeholders referencing earlier batch responses.

Multi-batch output
------------------
``reconcile_batches`` returns a list of ``BatchUpdateDocumentRequest`` objects.
Batches must be executed in order; any deferred-ID placeholders in a later
batch must be resolved against the responses from all prior batches using
``extradoc.reconcile_v3.executor.resolve_deferred_placeholders``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Document,
    Request,
)
from extradoc.api_types._generated import (
    List as DocList,
)
from extradoc.reconcile_v3.diff import diff_documents
from extradoc.reconcile_v3.lower import lower_batches

if TYPE_CHECKING:
    from extradoc.reconcile_v3.model import ReconcileOp


def _extract_lists_by_tab(doc: Document) -> dict[str, dict[str, DocList]]:
    """Extract tab_id → lists dict mapping from a Document.

    For legacy single-tab documents (no ``tabs`` field), uses empty string as
    tab_id (matching the pseudo-tab convention in diff.py).
    """
    if doc.tabs:
        result: dict[str, dict[str, DocList]] = {}
        for tab in doc.tabs:
            tab_id = ""
            if tab.tab_properties and tab.tab_properties.tab_id:
                tab_id = tab.tab_properties.tab_id
            doc_tab = tab.document_tab
            lists = (doc_tab.lists if doc_tab else None) or {}
            result[tab_id] = lists
        return result
    # Legacy document
    return {"": doc.lists or {}}


def reconcile(
    base: Document,
    desired: Document,
) -> list[Request]:
    """Top-down tree reconciler — single flat request list (first batch only).

    Parameters
    ----------
    base:
        Current state of the document.
    desired:
        Target state of the document.

    Returns
    -------
    list[Request]
        Flat list of typed request objects for the first (and usually only)
        batch.  If structural creation is needed (headers, tabs), call
        ``reconcile_batches`` instead to get the full multi-batch sequence.

    Notes
    -----
    If the diff requires multiple batches (e.g. creating a new header), this
    function returns only the first batch and will miss deferred-ID resolution.
    Use ``reconcile_batches`` for production use.
    """
    ops = diff_documents(base, desired)
    desired_lists_by_tab = _extract_lists_by_tab(desired)
    base_lists_by_tab = _extract_lists_by_tab(base)
    batches = lower_batches(
        ops,
        desired_lists_by_tab=desired_lists_by_tab,
        base_lists_by_tab=base_lists_by_tab,
    )
    if not batches:
        return []
    if len(batches) == 1:
        return batches[0]
    # Multiple batches: flatten for callers that expect a single list.
    # This is lossy (deferred IDs won't resolve), but is acceptable for simple
    # test scenarios where structural ops are not needed.
    return [req for batch in batches for req in batch]


def reconcile_batches(
    base: Document,
    desired: Document,
) -> list[BatchUpdateDocumentRequest]:
    """Top-down tree reconciler — multi-batch sequence.

    Parameters
    ----------
    base:
        Current state of the document.
    desired:
        Target state of the document.

    Returns
    -------
    list[BatchUpdateDocumentRequest]
        Ordered list of request batches.  Each batch must be executed in order.
        Deferred-ID placeholders in later batches are resolved against prior
        batch responses via
        ``extradoc.reconcile_v3.executor.resolve_deferred_placeholders``.
    """
    ops = diff_documents(base, desired)
    desired_lists_by_tab = _extract_lists_by_tab(desired)
    base_lists_by_tab = _extract_lists_by_tab(base)
    raw_batches = lower_batches(
        ops,
        desired_lists_by_tab=desired_lists_by_tab,
        base_lists_by_tab=base_lists_by_tab,
    )
    return [BatchUpdateDocumentRequest(requests=batch) for batch in raw_batches]


def diff(
    base: Document,
    desired: Document,
) -> list[ReconcileOp]:
    """Return the full op list for base → desired without lowering.

    Use this to verify op detection is correct without triggering lowering.
    """
    return diff_documents(base, desired)
