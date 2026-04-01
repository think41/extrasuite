"""Error types for ``reconcile_v2`` parse, diff, and lowering phases."""

from __future__ import annotations


class ReconcileV2Error(Exception):
    """Base exception for the semantic-IR reconciler."""


class ParseIRError(ReconcileV2Error):
    """Raised when transport JSON cannot be represented by the semantic IR."""


class UnsupportedReconcileV2Error(ReconcileV2Error):
    """Raised when ``reconcile_v2`` hits an explicit unsupported boundary.

    Use this for deliberate scope restrictions: operations the reconciler does
    not support (merged tables, multi-section new tabs, etc.).
    """


class ReconcileInvariantError(ReconcileV2Error):
    """Raised when an internal reconciler invariant is violated.

    This indicates a bug in the reconciler itself — the input was valid but
    an internal intermediate state was inconsistent.
    """
