"""Public interface for reconcile_v3.

reconcile_v3 is a top-down tree-oriented Google Docs reconciler built as a
self-contained in-memory experiment.  It does NOT integrate with the production
pipeline — use reconcile_v2 for production use.

Key differences from reconcile_v2:
- No ``transport_base`` parameter: v3 does not need an initial index fetch.
- Works directly with raw document dicts (no IR parse step).
- Top-down traversal with stable-ID matching at every tree level.
- Lowering produces one or more request batches; later batches use
  deferred-ID placeholders referencing earlier batch responses.

Multi-batch output
------------------
``reconcile_batches`` returns a list of request-batch lists.  Each batch is a
list of raw batchUpdate request dicts.  Batches must be executed in order; any
deferred-ID placeholders in a later batch must be resolved against the
responses from all prior batches using
``extradoc.reconcile_v2.executor.resolve_deferred_placeholders``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from extradoc.reconcile_v3.diff import diff_documents
from extradoc.reconcile_v3.lower import lower_batches

if TYPE_CHECKING:
    from extradoc.reconcile_v3.model import ReconcileOp


def _extract_lists_by_tab(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract tab_id → lists dict mapping from a document dict.

    For legacy single-tab documents (no ``tabs`` field), uses empty string as
    tab_id (matching the pseudo-tab convention in diff.py).
    """
    tabs = doc.get("tabs")
    if tabs:
        result: dict[str, dict[str, Any]] = {}
        for tab in tabs:
            props = tab.get("tabProperties") or {}
            tab_id = str(props.get("tabId", ""))
            doc_tab = tab.get("documentTab") or {}
            lists = doc_tab.get("lists") or {}
            result[tab_id] = lists
        return result
    # Legacy document
    return {"": doc.get("lists") or {}}


def reconcile(
    base: dict[str, Any],
    desired: dict[str, Any],
) -> list[dict[str, Any]]:
    """Top-down tree reconciler — single flat request list (first batch only).

    Parameters
    ----------
    base:
        Raw Google Docs API document dict (current state).
    desired:
        Raw Google Docs API document dict (target state).

    Returns
    -------
    list[dict[str, Any]]
        Flat list of raw batchUpdate request dicts for the first (and usually
        only) batch.  If structural creation is needed (headers, tabs), call
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
    # If only one batch, return it directly (common case)
    if len(batches) == 1:
        return batches[0]
    # Multiple batches: flatten for callers that expect a single list.
    # This is lossy (deferred IDs won't resolve), but is acceptable for simple
    # test scenarios where structural ops are not needed.
    return [req for batch in batches for req in batch]


def reconcile_batches(
    base: dict[str, Any],
    desired: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    """Top-down tree reconciler — multi-batch sequence.

    Parameters
    ----------
    base:
        Raw Google Docs API document dict (current state).
    desired:
        Raw Google Docs API document dict (target state).

    Returns
    -------
    list[list[dict[str, Any]]]
        Ordered list of request batches.  Each batch must be executed in order.
        Deferred-ID placeholders in later batches are resolved against prior
        batch responses via
        ``extradoc.reconcile_v2.executor.resolve_deferred_placeholders``.
    """
    ops = diff_documents(base, desired)
    desired_lists_by_tab = _extract_lists_by_tab(desired)
    base_lists_by_tab = _extract_lists_by_tab(base)
    return lower_batches(
        ops,
        desired_lists_by_tab=desired_lists_by_tab,
        base_lists_by_tab=base_lists_by_tab,
    )


def diff(
    base: dict[str, Any],
    desired: dict[str, Any],
) -> list[ReconcileOp]:
    """Return the full op list for base → desired without lowering.

    Use this to verify op detection is correct without triggering lowering.
    """
    return diff_documents(base, desired)
