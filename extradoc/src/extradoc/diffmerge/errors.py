"""Error types for reconcile_v3."""

from __future__ import annotations


class ReconcileV3Error(Exception):
    """Base exception for the top-down tree reconciler."""


class UnsupportedReconcileV3Error(ReconcileV3Error):
    """Raised when reconcile_v3 hits a deliberate unsupported boundary.

    Examples: DocumentStyle changed, InlineObject changed, list content edited.
    These cannot be expressed via batchUpdate and require manual intervention.
    """


class ReconcileV3InvariantError(ReconcileV3Error):
    """Raised when an internal reconciler invariant is violated (a bug)."""


class CoordinateNotResolvedError(ReconcileV3Error):
    """Raised when reconcile_v3/lower encounters a desired-tree node whose
    (startIndex, endIndex) are None and the current code path cannot
    synthesize a live-doc coordinate from base anchors + cumulative shift.

    Also raised when a base-tree node is unexpectedly missing concrete
    indices — the coordinate contract (docs/coordinate_contract.md) requires
    the base tree to always be in State A (concrete).

    See ``docs/coordinate_contract.md`` §failure-mode.
    """
