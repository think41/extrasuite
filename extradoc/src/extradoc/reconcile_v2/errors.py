"""Error types for ``reconcile_v2`` parse, diff, and lowering phases."""

from __future__ import annotations


class ReconcileV2Error(Exception):
    """Base exception for the in-progress semantic-IR reconciler."""


class ParseIRError(ReconcileV2Error):
    """Raised when transport JSON cannot be represented by the spike IR."""


class UnsupportedSpikeError(ReconcileV2Error):
    """Raised when the confidence-sprint parser hits an unsupported construct."""
