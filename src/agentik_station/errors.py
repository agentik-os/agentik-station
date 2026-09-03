from __future__ import annotations


class StationError(RuntimeError):
    """Base Station error with an actionable message."""


class ValidationError(StationError):
    """Invalid desired state or identifier."""


class SecurityError(StationError):
    """A filesystem, command, or trust-boundary safety check failed."""


class ReconcileError(StationError):
    """Desired state could not be reconciled."""
