"""DeepAgents tool-result safety inspection primitives.

The public inspection APIs load on demand so base providers do not require the
optional DeepAgents/LangChain dependencies merely to import error types.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from lightspeed_agentic.inspection.errors import (
    CLASSIFIER_FAILURE_MESSAGE,
    InspectionError,
    ToolResultSafetyInspectionFailed,
)

_LAZY_EXPORTS = {
    "ClassifierClient": ("lightspeed_agentic.inspection.inspector", "ClassifierClient"),
    "ClassifierDecision": ("lightspeed_agentic.inspection.models", "ClassifierDecision"),
    "ClassifierRequest": ("lightspeed_agentic.inspection.models", "ClassifierRequest"),
    "InspectionResult": ("lightspeed_agentic.inspection.inspector", "InspectionResult"),
    "LangChainClassifierClient": (
        "lightspeed_agentic.inspection.client",
        "LangChainClassifierClient",
    ),
    "inspect_tool_result": (
        "lightspeed_agentic.inspection.inspector",
        "inspect_tool_result",
    ),
}

__all__ = [
    "CLASSIFIER_FAILURE_MESSAGE",
    "ClassifierClient",
    "ClassifierDecision",
    "ClassifierRequest",
    "InspectionError",
    "InspectionResult",
    "LangChainClassifierClient",
    "ToolResultSafetyInspectionFailed",
    "inspect_tool_result",
]


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
