"""DevFlow MainAgent module - lazy export to avoid circular imports."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from deerflow.devflow.main_agent.orchestrator import DevFlowOrchestrator
    from deerflow.devflow.main_agent.prompt import MAIN_AGENT_PROMPT
    from deerflow.devflow.main_agent.state import (
        HumanDecisionRequest,
        HumanDecisionStatus,
        PipelineStage,
        PipelineState,
        PipelineStatus,
    )

__all__ = [
    "DevFlowOrchestrator",
    "MAIN_AGENT_PROMPT",
    "PipelineStage",
    "PipelineStatus",
    "PipelineState",
    "HumanDecisionRequest",
    "HumanDecisionStatus",
]


def __getattr__(name: str):
    """Lazy attribute access so that importing this module does not pull in
    :mod:`deerflow.devflow.main_agent.orchestrator` (which would form a
    circular dependency with :mod:`deerflow.devflow.agents.base`)."""
    if name == "DevFlowOrchestrator":
        from deerflow.devflow.main_agent.orchestrator import DevFlowOrchestrator

        return DevFlowOrchestrator
    if name == "MAIN_AGENT_PROMPT":
        from deerflow.devflow.main_agent.prompt import MAIN_AGENT_PROMPT

        return MAIN_AGENT_PROMPT
    if name in {"PipelineStage", "PipelineStatus", "PipelineState", "HumanDecisionRequest", "HumanDecisionStatus"}:
        from deerflow.devflow.main_agent import state as _state

        return getattr(_state, name)
    raise AttributeError(name)
