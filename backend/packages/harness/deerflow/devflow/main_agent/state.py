"""Enhanced pipeline state definitions with loop subgraph and human-interaction support.

This module defines the canonical state for the DevFlow multi-agent pipeline:

    requirements -> architecture -> frontend_design -> { spec_development -> code_testing -> deployment }*

The three trailing stages (spec/test/deploy) form a *loop subgraph* that
iterates until the test report is green, the deployment validates, the user
exits early, or the configured iteration ceiling is reached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PipelineStage(str, Enum):
    """Linear stages executed in order at the head of the pipeline.

    Only TWO linear stages remain:

    * ``requirements`` - turns the user task into a combined PRD +
      architecture document. (Architecture is folded into the same agent
      because the two concerns are too tightly coupled to be worth
      splitting into separate stages.)
    * ``frontend_design`` - turns the requirements artifact into a
      frontend design package that the loop subgraph consumes.
    """

    REQUIREMENTS = "requirements"
    FRONTEND_DESIGN = "frontend_design"
    SPEC_DEVELOPMENT = "spec_development"
    CODE_TESTING = "code_testing"
    DEPLOYMENT = "deployment"


class LoopStage(str, Enum):
    """Members of the iterative spec -> test -> deploy loop subgraph."""

    SPEC_DEVELOPMENT = "spec_development"
    CODE_TESTING = "code_testing"
    DEPLOYMENT = "deployment"


class PipelineStatus(str, Enum):
    """High-level pipeline status values reported to the UI."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    WAITING_HUMAN_DECISION = "waiting_human_decision"
    CONTINUING_CONVERSATION = "continuing_conversation"


class HumanDecisionStatus(str, Enum):
    """Status of a single human decision request."""

    PENDING = "pending"
    ANSWERED = "answered"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class LoopExitReason(str, Enum):
    """Why the spec->test->deploy loop subgraph terminated."""

    TESTS_PASSED = "tests_passed"
    DEPLOYMENT_VALIDATED = "deployment_validated"
    MAX_ITERATIONS = "max_iterations"
    HUMAN_DECISION = "human_decision"
    PIPELINE_CANCELLED = "pipeline_cancelled"
    ESCALATED = "escalated"


@dataclass
class StageResult:
    """Outcome produced by a single stage execution."""

    stage: PipelineStage
    success: bool
    output: str
    files: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    iteration_count: int = 1


@dataclass
class HumanDecisionRequest:
    """A standardized request for a human to make a decision.

    See ``HumanDecisionManager`` for the formatting / lifecycle.
    """

    id: str
    stage: str
    question: str
    background: str
    options: list[dict[str, str]]  # [{label, description, recommendation}]
    recommended_option: str | None = None
    deadline: str | None = None
    status: HumanDecisionStatus = HumanDecisionStatus.PENDING
    answer: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    answered_at: datetime | None = None


@dataclass
class ConversationState:
    """State of a non-decision conversation that an agent is having with the user."""

    conversation_id: str
    agent_name: str
    stage: str
    task_status: str  # "in_progress" | "completed" | "blocked"
    pending_actions: list[str] = field(default_factory=list)
    continuation_reason: str = ""
    max_continuations: int = 3
    continuation_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)

    def can_continue(self) -> bool:
        return self.continuation_count < self.max_continuations

    def increment_continuation(self) -> None:
        self.continuation_count += 1
        self.last_updated = datetime.now()


@dataclass
class LoopIterationRecord:
    """One full pass through the spec->test->deploy loop."""

    iteration: int
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    test_passed: bool = False
    deployment_validated: bool = False
    exit_reason: LoopExitReason | None = None
    notes: str = ""


@dataclass
class PipelineState:
    """Top-level state of one DevFlow pipeline instance."""

    project_id: str
    name: str
    description: str
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: PipelineStage = PipelineStage.REQUIREMENTS
    completed_stages: list[StageResult] = field(default_factory=list)
    failed_stage: StageResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Loop subgraph state
    loop_iteration: int = 0
    max_loop_iterations: int = 5
    loop_stages_completed: list[str] = field(default_factory=list)
    loop_history: list[LoopIterationRecord] = field(default_factory=list)
    loop_exit_reason: LoopExitReason | None = None

    # Human interaction state
    pending_decisions: list[HumanDecisionRequest] = field(default_factory=list)
    active_conversations: dict[str, ConversationState] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers
    def get_stage_result(self, stage: PipelineStage) -> StageResult | None:
        for result in self.completed_stages:
            if result.stage == stage:
                return result
        return None

    def mark_stage_completed(self, result: StageResult) -> None:
        result.completed_at = datetime.now()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        self.completed_stages.append(result)
        stage_order = list(PipelineStage)
        current_idx = stage_order.index(self.current_stage)
        if current_idx < len(stage_order) - 1:
            self.current_stage = stage_order[current_idx + 1]

    def mark_failed(self, result: StageResult) -> None:
        result.completed_at = datetime.now()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        self.failed_stage = result
        self.status = PipelineStatus.FAILED
        self.completed_at = result.completed_at

    def mark_completed(self) -> None:
        self.status = PipelineStatus.COMPLETED
        self.completed_at = datetime.now()

    def add_decision_request(self, request: HumanDecisionRequest) -> None:
        self.pending_decisions.append(request)
        self.status = PipelineStatus.WAITING_HUMAN_DECISION

    def resolve_decision(self, decision_id: str, answer: str) -> HumanDecisionRequest | None:
        for decision in self.pending_decisions:
            if decision.id == decision_id:
                decision.answer = answer
                decision.status = HumanDecisionStatus.ANSWERED
                decision.answered_at = datetime.now()
                self.status = PipelineStatus.RUNNING
                return decision
        return None

    # ------------------------------------------------------------------ loop
    def start_loop_iteration(self) -> int:
        self.loop_iteration += 1
        self.loop_stages_completed = []
        self.loop_history.append(LoopIterationRecord(iteration=self.loop_iteration))
        return self.loop_iteration

    def record_loop_iteration_result(
        self,
        *,
        test_passed: bool,
        deployment_validated: bool,
        exit_reason: LoopExitReason,
        notes: str = "",
    ) -> None:
        if not self.loop_history:
            return
        record = self.loop_history[-1]
        record.completed_at = datetime.now()
        record.test_passed = test_passed
        record.deployment_validated = deployment_validated
        record.exit_reason = exit_reason
        record.notes = notes
        if exit_reason != LoopExitReason.MAX_ITERATIONS:
            self.loop_exit_reason = exit_reason

    def mark_loop_stage_completed(self, stage: LoopStage) -> None:
        if stage.value not in self.loop_stages_completed:
            self.loop_stages_completed.append(stage.value)

    def is_loop_complete(self) -> bool:
        return all(stage.value in self.loop_stages_completed for stage in LoopStage)

    def should_retry_loop(self, test_artifact_content: str) -> bool:
        """Decide whether the loop should iterate again.

        The loop retries when there are test failures, deployment validation
        failures, or the user explicitly asked for a retry - as long as we are
        still below ``max_loop_iterations``.
        """
        lowered = test_artifact_content.lower()
        has_test_failures = "failed" in lowered or "error" in lowered
        has_deploy_issues = "deployment_invalid" in lowered or "deploy_failed" in lowered
        return (has_test_failures or has_deploy_issues) and self.loop_iteration < self.max_loop_iterations

    # ----------------------------------------------------------------- export
    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "current_stage": self.current_stage.value,
            "completed_stages": [
                {
                    "stage": r.stage.value,
                    "success": r.success,
                    "output": r.output,
                    "files": r.files,
                    "error": r.error,
                    "started_at": r.started_at.isoformat(),
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "duration_seconds": r.duration_seconds,
                    "iteration_count": r.iteration_count,
                }
                for r in self.completed_stages
            ],
            "failed_stage": (
                {
                    "stage": self.failed_stage.stage.value,
                    "error": self.failed_stage.error,
                }
                if self.failed_stage
                else None
            ),
            "loop_iteration": self.loop_iteration,
            "max_loop_iterations": self.max_loop_iterations,
            "loop_stages_completed": self.loop_stages_completed,
            "loop_history": [
                {
                    "iteration": r.iteration,
                    "started_at": r.started_at.isoformat(),
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "test_passed": r.test_passed,
                    "deployment_validated": r.deployment_validated,
                    "exit_reason": r.exit_reason.value if r.exit_reason else None,
                    "notes": r.notes,
                }
                for r in self.loop_history
            ],
            "loop_exit_reason": self.loop_exit_reason.value if self.loop_exit_reason else None,
            "pending_decisions": [
                {
                    "id": d.id,
                    "stage": d.stage,
                    "question": d.question,
                    "background": d.background,
                    "options": d.options,
                    "recommended_option": d.recommended_option,
                    "status": d.status.value,
                }
                for d in self.pending_decisions
            ],
            "active_conversations": {
                cid: {
                    "agent_name": c.agent_name,
                    "stage": c.stage,
                    "task_status": c.task_status,
                    "continuation_count": c.continuation_count,
                    "max_continuations": c.max_continuations,
                    "pending_actions": c.pending_actions,
                    "continuation_reason": c.continuation_reason,
                }
                for cid, c in self.active_conversations.items()
            },
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
