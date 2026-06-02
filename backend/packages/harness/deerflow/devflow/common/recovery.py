"""Error classification and recovery utilities for DevFlow.

This module provides:

* :class:`ErrorClassifier` - categorises a failure (agent error / tool error
  / memory error / context-too-large / etc.) and returns a
  :class:`RecoveryAction` describing what the orchestrator should do next.
* :func:`async_retry` - an async retry decorator with exponential backoff.
* :class:`PartialOutput` - a structured way for an agent to declare
  "I have partial output, please continue with this".
* :class:`TraceContext` - a small context manager that yields a stable
  ``trace_id`` for a stage run, used in the SSE events.
"""
from __future__ import annotations

import asyncio
import functools
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Iterator, TypeVar

from deerflow.devflow.common.exceptions import (
    DevFlowError,
    MemoryStorageError,
    TaskOrchestrationError,
)
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("recovery")

T = TypeVar("T")


class ErrorKind(str, Enum):
    AGENT_EXECUTION = "agent_execution"
    TOOL_EXECUTION = "tool_execution"
    MEMORY_STORAGE = "memory_storage"
    CONTEXT_TOO_LARGE = "context_too_large"
    HUMAN_DECISION_TIMEOUT = "human_decision_timeout"
    LOOP_MAX_ITERATIONS = "loop_max_iterations"
    USER_CANCELLED = "user_cancelled"
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    RETRY_STAGE = "retry_stage"
    RETRY_TOOL = "retry_tool"
    USE_PARTIAL_OUTPUT = "use_partial_output"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    TIMEOUT_FALLBACK = "timeout_fallback"
    EXIT_LOOP = "exit_loop"
    FAIL_PIPELINE = "fail_pipeline"
    SKIP_AND_CONTINUE = "skip_and_continue"


@dataclass
class ErrorClassification:
    kind: ErrorKind
    action: RecoveryAction
    severity: str  # "low" | "medium" | "high"
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ErrorClassifier:
    """Map an exception (or string error) to a :class:`ErrorClassification`."""

    def classify(self, error: Exception | str) -> ErrorClassification:
        message = str(error)
        lowered = message.lower()

        if isinstance(error, MemoryStorageError):
            return ErrorClassification(
                kind=ErrorKind.MEMORY_STORAGE,
                action=RecoveryAction.RETRY_STAGE,
                severity="high",
                message=message,
            )
        if isinstance(error, TaskOrchestrationError):
            return ErrorClassification(
                kind=ErrorKind.AGENT_EXECUTION,
                action=RecoveryAction.ESCALATE_TO_HUMAN,
                severity="high",
                message=message,
            )
        if "context" in lowered and ("too long" in lowered or "exceed" in lowered or "tokens" in lowered):
            return ErrorClassification(
                kind=ErrorKind.CONTEXT_TOO_LARGE,
                action=RecoveryAction.USE_PARTIAL_OUTPUT,
                severity="low",
                message=message,
            )
        if "tool" in lowered or "shell" in lowered or "command" in lowered:
            return ErrorClassification(
                kind=ErrorKind.TOOL_EXECUTION,
                action=RecoveryAction.RETRY_TOOL,
                severity="medium",
                message=message,
            )
        if "timeout" in lowered and "decision" in lowered:
            return ErrorClassification(
                kind=ErrorKind.HUMAN_DECISION_TIMEOUT,
                action=RecoveryAction.TIMEOUT_FALLBACK,
                severity="medium",
                message=message,
            )
        if "cancelled" in lowered or "canceled" in lowered:
            return ErrorClassification(
                kind=ErrorKind.USER_CANCELLED,
                action=RecoveryAction.FAIL_PIPELINE,
                severity="low",
                message=message,
            )
        if isinstance(error, DevFlowError) or "agent" in lowered or "stage" in lowered:
            return ErrorClassification(
                kind=ErrorKind.AGENT_EXECUTION,
                action=RecoveryAction.RETRY_STAGE,
                severity="high",
                message=message,
            )
        return ErrorClassification(
            kind=ErrorKind.UNKNOWN,
            action=RecoveryAction.RETRY_STAGE,
            severity="medium",
            message=message,
        )


# --------------------------------------------------------------- async_retry
def async_retry(
    *,
    max_attempts: int = 2,
    backoff_seconds: float = 0.1,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Async retry decorator with linear backoff."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as exc:
                    last_exc = exc
                    if attempt >= max_attempts:
                        break
                    wait = backoff_seconds * attempt
                    logger.warning(
                        "async_retry: %s attempt %d failed (%s); retrying in %.2fs",
                        getattr(func, "__name__", "callable"),
                        attempt,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


# --------------------------------------------------------------- partial output
@dataclass
class PartialOutput:
    """Structured declaration that an agent produced partial output."""

    stage: str
    content: str
    files: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    missing_steps: list[str] = field(default_factory=list)
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "content": self.content,
            "files": self.files,
            "completed_steps": self.completed_steps,
            "missing_steps": self.missing_steps,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
        }


# --------------------------------------------------------------- trace context
@contextmanager
def trace_context(prefix: str = "trace") -> Iterator[str]:
    """Yield a short trace id usable for log correlation / SSE event metadata."""
    trace_id = f"{prefix}-{uuid.uuid4().hex[:10]}"
    logger.debug("trace begin: %s", trace_id)
    try:
        yield trace_id
    finally:
        logger.debug("trace end: %s", trace_id)
