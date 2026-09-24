"""Safe inspection error types."""

from __future__ import annotations

CLASSIFIER_FAILURE_MESSAGE = (
    "Lightspeed stopped the operation because a tool result failed the safety inspection."
)


class InspectionError(RuntimeError):
    """A classifier failure that carries no untrusted content."""

    def __init__(
        self,
        message: str = CLASSIFIER_FAILURE_MESSAGE,
        *,
        failure_type: str = "provider_error",
        attempt_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.attempt_count = attempt_count
