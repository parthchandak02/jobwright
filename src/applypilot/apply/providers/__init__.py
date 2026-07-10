"""Agent provider plugins for stage-6 browser apply."""

from applypilot.apply.providers.base import (
    AgentProvider,
    ApplyOutcome,
    ApplyResult,
    WorkerContext,
    get_provider,
    parse_result_output,
)

__all__ = [
    "AgentProvider",
    "ApplyOutcome",
    "ApplyResult",
    "WorkerContext",
    "get_provider",
    "parse_result_output",
]
