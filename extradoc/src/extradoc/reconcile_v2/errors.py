"""Error types for ``reconcile_v2`` parse, diff, and lowering phases."""

from __future__ import annotations


class ReconcileV2Error(Exception):
    """Base exception for the semantic-IR reconciler."""


class ParseIRError(ReconcileV2Error):
    """Raised when transport JSON cannot be represented by the semantic IR."""


class UnsupportedReconcileV2Error(ReconcileV2Error):
    """Raised when ``reconcile_v2`` hits an explicit unsupported boundary."""


# Backward-compatible alias for older tests and internal imports.
UnsupportedSpikeError = UnsupportedReconcileV2Error
