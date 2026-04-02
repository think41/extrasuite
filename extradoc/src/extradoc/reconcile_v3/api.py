"""Public interface for reconcile_v3.

reconcile_v3 is a top-down tree-oriented Google Docs reconciler built as a
self-contained in-memory experiment.  It does NOT integrate with the production
pipeline — use reconcile_v2 for production use.

Key differences from reconcile_v2:
- No ``transport_base`` parameter: v3 does not need an initial index fetch.
- Works directly with raw document dicts (no IR parse step).
- Top-down traversal with stable-ID matching at every tree level.
- Lowering is stubbed (raises NotImplementedError) for this experiment; the
  diff pass is the proven artifact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from extradoc.reconcile_v3.diff import diff_documents
from extradoc.reconcile_v3.lower import lower_ops

if TYPE_CHECKING:
    from extradoc.reconcile_v3.model import ReconcileOp


def reconcile(
    base: dict[str, Any],
    desired: dict[str, Any],
) -> list[dict[str, Any]]:
    """Top-down tree reconciler.

    Parameters
    ----------
    base:
        Raw Google Docs API document dict (current state).
    desired:
        Raw Google Docs API document dict (target state).

    Returns
    -------
    list[dict[str, Any]]
        List of raw batchUpdate request dicts.

    Notes
    -----
    This experiment iteration stubs all lowering with ``NotImplementedError``.
    Callers should use :func:`diff` to retrieve ops without lowering for now.
    """
    ops = diff_documents(base, desired)
    return lower_ops(ops)


def diff(
    base: dict[str, Any],
    desired: dict[str, Any],
) -> list[ReconcileOp]:
    """Return the full op list for base → desired without lowering.

    Use this during the experiment phase to verify op detection is correct
    before lowering is implemented.
    """
    return diff_documents(base, desired)
