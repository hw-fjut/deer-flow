"""Main pipeline orchestrator.

The orchestrator drives the *DevFlow* pipeline:

    requirements -> frontend_design
        -> { spec_development -> code_testing -> deployment }*

The first two stages are linear; the trailing two are a *loop subgraph*
that the orchestrator iterates until the tests pass, the deployment
validates, the user exits early, or the iteration ceiling is reached.

Per-stage context is filtered through :meth:`_build_stage_context` so that
loop-subgraph agents see *only* the frontend-design output and the previous
loop iteration result - never the requirements / frontend-design conversation
history.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
# NOTE: agent registry is resolved lazily inside ``_get_agent_for_stage`` to
# avoid a circular import with ``deerflow.devflow.agents``.
from deerflow.devflow.common.conversation_state import (
    ChatMessage,
    ChatSession,
    ChatSessionManager,
)
from deerflow.devflow.common.conversation_state import (
    ConversationStateManager,
    ConversationTrigger,
)
from deerflow.devflow.common.exceptions import PipelineError, TaskOrchestrationError
from deerflow.devflow.common.human_decision import HumanDecisionManager
from deerflow.devflow.common.logging import setup_logger
from deerflow.devflow.common.skill_config import get_skill_loader
from deerflow.devflow.main_agent.state import (
    ConversationState,
    HumanDecisionRequest,
    HumanDecisionStatus,
    LoopExitReason,
    LoopStage,
    PipelineStage,
    PipelineState,
    PipelineStatus,
    StageResult,
)
from deerflow.devflow.memory.service import MemoryService

logger = setup_logger("orchestrator")


# Stage access policy. Loop-subgraph agents are *isolated* and only get the
# frontend_design output plus the previous loop iteration's output.
LOOP_STAGE_ACCESS: dict[PipelineStage, str] = {
    PipelineStage.SPEC_DEVELOPMENT: "frontend_design_only",
    PipelineStage.CODE_TESTING: "frontend_design_and_spec",
    PipelineStage.DEPLOYMENT: "frontend_design_and_testing",
}

LINEAR_STAGES: tuple[PipelineStage, ...] = (
    PipelineStage.REQUIREMENTS,
    PipelineStage.FRONTEND_DESIGN,
)

LOOP_STAGES: tuple[PipelineStage, ...] = (
    PipelineStage.SPEC_DEVELOPMENT,
    PipelineStage.CODE_TESTING,
    PipelineStage.DEPLOYMENT,
)


class DevFlowOrchestrator:
    """DevFlow task orchestrator with loop subgraph and human-interaction support."""

    def __init__(
        self,
        memory_service: MemoryService | None = None,
        decision_manager: HumanDecisionManager | None = None,
        conversation_manager: ConversationStateManager | None = None,
        skill_loader=None,
        chat_manager: ChatSessionManager | None = None,
        *,
        max_loop_iterations: int = 5,
        max_conversation_continuations: int = 3,
        default_decision_timeout_hours: int = 24,
    ):
        self.memory = memory_service or MemoryService()
        self.decision_manager = decision_manager or HumanDecisionManager(default_decision_timeout_hours)
        self.conversation_manager = conversation_manager or ConversationStateManager(
            max_continuations=max_conversation_continuations
        )
        self.skill_loader = skill_loader or get_skill_loader()
        self.chat_manager = chat_manager or ChatSessionManager()
        self.max_loop_iterations = max_loop_iterations
        self.active_pipelines: dict[str, PipelineState] = {}
        # Decision responses that arrived while the pipeline was paused.
        self._pending_decision_answers: dict[str, str] = {}

    # ============================================================== lifecycle
    async def start_pipeline(self, name: str, description: str) -> PipelineState:
        project = await self.memory.create_project(name, description)
        state = PipelineState(
            project_id=project.project_id,
            name=name,
            description=description,
            status=PipelineStatus.RUNNING,
            started_at=datetime.now(),
            max_loop_iterations=self.max_loop_iterations,
        )
        self.active_pipelines[project.project_id] = state
        logger.info("Started pipeline: %s (%s)", name, project.project_id)
        return state

    async def cancel_pipeline(self, project_id: str, reason: str = "user_cancelled") -> None:
        state = self.active_pipelines.get(project_id)
        if not state:
            return
        state.status = PipelineStatus.FAILED
        state.completed_at = datetime.now()
        if state.loop_history:
            state.record_loop_iteration_result(
                test_passed=False,
                deployment_validated=False,
                exit_reason=LoopExitReason.PIPELINE_CANCELLED,
                notes=reason,
            )
        logger.info("Pipeline %s cancelled: %s", project_id, reason)

    # ================================================================ execution
    async def execute_pipeline(self, project_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Run the pipeline, yielding SSE-style events."""
        state = self.active_pipelines.get(project_id)
        if not state:
            raise TaskOrchestrationError(f"Pipeline not found: {project_id}")

        # Apply any decision answers that arrived while we were paused.
        for did, answer in list(self._pending_decision_answers.items()):
            state.resolve_decision(did, answer)
            self._pending_decision_answers.pop(did, None)

        try:
            context = await self.memory.get_project_context(project_id)

            # ---- Phase 1: linear stages
            for stage in LINEAR_STAGES:
                if state.get_stage_result(stage):
                    continue
                state.current_stage = stage
                async for event in self._run_linear_stage(project_id, stage, context, state):
                    if event.get("type") == "pause":
                        return
                    yield event
                    if event.get("type") == "stage_complete":
                        context = await self.memory.get_project_context(project_id)

            # ---- Phase 2: loop subgraph
            async for event in self._run_loop_subgraph(project_id, state, context):
                if event.get("type") == "pause":
                    return
                yield event
                if event.get("type") in {"stage_complete", "loop_retry"}:
                    context = await self.memory.get_project_context(project_id)

            state.mark_completed()
            yield {
                "type": "pipeline_complete",
                "project_id": project_id,
                "status": state.to_dict(),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.exception("Pipeline %s failed: %s", project_id, e)
            state.status = PipelineStatus.FAILED
            state.completed_at = datetime.now()
            yield {
                "type": "pipeline_error",
                "project_id": project_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    # ----------------------------------------------------------------- linear
    async def _run_linear_stage(
        self,
        project_id: str,
        stage: PipelineStage,
        context: dict[str, Any],
        state: PipelineState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        yield {
            "type": "stage_start",
            "project_id": project_id,
            "stage": stage.value,
            "timestamp": datetime.now().isoformat(),
        }

        stage_context = self._build_stage_context(stage, context)
        agent = self._get_agent_for_stage(stage)
        result = await self._execute_stage(project_id, stage, stage_context, state, agent=agent)

        # Mid-task human decision?
        if result.human_decision:
            async for ev in self._handle_human_decision(project_id, stage, result, state):
                yield ev
            return
        # Mid-task conversation continuation?
        if result.conversation_continuation:
            async for ev in self._handle_conversation_continuation(project_id, stage, result, state):
                yield ev
            return

        if result.success:
            stage_result = self._to_stage_result(stage, result, loop_iteration=1)
            state.mark_stage_completed(stage_result)
            await self.memory.save_stage_artifact(
                project_id=project_id,
                stage=stage.value,
                name=f"{stage.value}_output",
                content=result.result,
                files=result.files,
                metadata=result.metadata,
            )
            yield {
                "type": "stage_complete",
                "project_id": project_id,
                "stage": stage.value,
                "output": result.result[:500],
                "files": result.files,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            state.mark_failed(self._to_stage_result(stage, result, loop_iteration=1))
            yield {
                "type": "stage_failed",
                "project_id": project_id,
                "stage": stage.value,
                "error": result.error,
                "timestamp": datetime.now().isoformat(),
            }
            yield {"type": "pause", "reason": "stage_failed"}
            return

    # ------------------------------------------------------------------- loop
    async def _run_loop_subgraph(
        self,
        project_id: str,
        state: PipelineState,
        context: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the iterative spec->test->deploy subgraph."""
        loop_iteration = 0
        while loop_iteration < state.max_loop_iterations:
            loop_iteration += 1
            state.start_loop_iteration()
            yield {
                "type": "loop_start",
                "project_id": project_id,
                "iteration": loop_iteration,
                "timestamp": datetime.now().isoformat(),
            }

            test_passed = False
            deployment_validated = False
            exit_reason: LoopExitReason | None = None
            notes_parts: list[str] = []

            for stage in LOOP_STAGES:
                if LoopStage(stage.value).value in state.loop_stages_completed:
                    continue
                state.current_stage = stage
                stage_context = self._build_stage_context(stage, context, state)
                agent = self._get_agent_for_stage(stage)

                yield {
                    "type": "stage_start",
                    "project_id": project_id,
                    "stage": stage.value,
                    "iteration": loop_iteration,
                    "timestamp": datetime.now().isoformat(),
                }

                result = await self._execute_stage(
                    project_id, stage, stage_context, state, agent=agent, loop_iteration=loop_iteration
                )

                if result.human_decision:
                    async for ev in self._handle_human_decision(project_id, stage, result, state):
                        yield ev
                    state.record_loop_iteration_result(
                        test_passed=False,
                        deployment_validated=False,
                        exit_reason=LoopExitReason.HUMAN_DECISION,
                        notes="paused for human decision",
                    )
                    return

                if result.conversation_continuation:
                    async for ev in self._handle_conversation_continuation(
                        project_id, stage, result, state
                    ):
                        yield ev
                    # If we are escalated to a decision, pause.
                    if result.metadata.get("pause_reason") == "conversation_exhausted":
                        state.record_loop_iteration_result(
                            test_passed=False,
                            deployment_validated=False,
                            exit_reason=LoopExitReason.ESCALATED,
                            notes="conversation exhausted -> escalated",
                        )
                        return

                if not result.success:
                    state.mark_failed(self._to_stage_result(stage, result, loop_iteration=loop_iteration))
                    yield {
                        "type": "stage_failed",
                        "project_id": project_id,
                        "stage": stage.value,
                        "iteration": loop_iteration,
                        "error": result.error,
                        "timestamp": datetime.now().isoformat(),
                    }
                    yield {"type": "pause", "reason": "stage_failed"}
                    return

                stage_result = self._to_stage_result(stage, result, loop_iteration=loop_iteration)
                state.mark_stage_completed(stage_result)
                state.mark_loop_stage_completed(LoopStage(stage.value))
                await self.memory.save_stage_artifact(
                    project_id=project_id,
                    stage=stage.value,
                    name=f"{stage.value}_iter{loop_iteration}_output",
                    content=result.result,
                    files=result.files,
                    metadata={**(result.metadata or {}), "iteration": loop_iteration},
                )
                context = await self.memory.get_project_context(project_id)
                yield {
                    "type": "stage_complete",
                    "project_id": project_id,
                    "stage": stage.value,
                    "iteration": loop_iteration,
                    "output": result.result[:500],
                    "files": result.files,
                    "timestamp": datetime.now().isoformat(),
                }

                if stage == PipelineStage.CODE_TESTING:
                    test_passed = self._is_test_report_green(result.result)
                    notes_parts.append(f"tests_passed={test_passed}")
                elif stage == PipelineStage.DEPLOYMENT:
                    deployment_validated = self._is_deployment_valid(result.result)
                    notes_parts.append(f"deployment_validated={deployment_validated}")

            # ---- decide whether to iterate
            if test_passed and deployment_validated:
                exit_reason = LoopExitReason.TESTS_PASSED
                state.record_loop_iteration_result(
                    test_passed=True,
                    deployment_validated=True,
                    exit_reason=exit_reason,
                    notes="; ".join(notes_parts),
                )
                yield {
                    "type": "loop_complete",
                    "project_id": project_id,
                    "iteration": loop_iteration,
                    "reason": exit_reason.value,
                    "timestamp": datetime.now().isoformat(),
                }
                return
            if loop_iteration >= state.max_loop_iterations:
                exit_reason = LoopExitReason.MAX_ITERATIONS
                state.record_loop_iteration_result(
                    test_passed=test_passed,
                    deployment_validated=deployment_validated,
                    exit_reason=exit_reason,
                    notes="; ".join(notes_parts),
                )
                yield {
                    "type": "loop_retry_exhausted",
                    "project_id": project_id,
                    "iteration": loop_iteration,
                    "reason": exit_reason.value,
                    "timestamp": datetime.now().isoformat(),
                }
                return

            # Otherwise: retry
            yield {
                "type": "loop_retry",
                "project_id": project_id,
                "iteration": loop_iteration,
                "reason": "tests or deployment not green, retrying loop",
                "test_passed": test_passed,
                "deployment_validated": deployment_validated,
                "timestamp": datetime.now().isoformat(),
            }
            # Reset loop_stages_completed so the next iteration re-runs them.
            state.loop_stages_completed = []

    # ----------------------------------------------------------- stage runner
    async def _execute_stage(
        self,
        project_id: str,
        stage: PipelineStage,
        stage_context: dict[str, Any],
        state: PipelineState,
        agent: BaseSubAgent | None = None,
        loop_iteration: int = 1,
    ) -> AgentOutput:
        started_at = datetime.now()
        try:
            agent = agent or self._get_agent_for_stage(stage)
            agent_input = AgentInput(
                task=f"Execute {stage.value} stage for project: {stage_context.get('name', project_id)}",
                context=stage_context,
                previous_artifacts=stage_context.get("artifacts", {}),
                allowed_stages=[stage.value],
                trace_id=f"{project_id}-{stage.value}-{loop_iteration}-{uuid.uuid4().hex[:6]}",
            )

            # Retry once on transient failures.
            last_error: str | None = None
            for attempt in range(2):
                try:
                    output = await agent.execute(agent_input)
                    output.metadata.setdefault("attempt", attempt + 1)
                    output.metadata.setdefault("loop_iteration", loop_iteration)
                    return output
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    logger.warning(
                        "Stage %s attempt %d failed: %s", stage.value, attempt + 1, exc
                    )
                    if attempt == 0:
                        await asyncio.sleep(0.1 * (attempt + 1))

            return AgentOutput(
                result="",
                success=False,
                error=f"Stage {stage.value} failed after retries: {last_error}",
                metadata={"stage": stage.value, "started_at": started_at.isoformat()},
            )
        except Exception as e:  # pragma: no cover - safety net
            logger.exception("Stage %s crashed: %s", stage.value, e)
            return AgentOutput(
                result="",
                success=False,
                error=str(e),
                metadata={"stage": stage.value, "started_at": started_at.isoformat()},
            )

    # ----------------------------------------------------- human interaction
    async def _handle_human_decision(
        self,
        project_id: str,
        stage: PipelineStage,
        result: AgentOutput,
        state: PipelineState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload = result.human_decision or {}
        decision = HumanDecisionRequest(
            id=payload.get("id", f"dec-{uuid.uuid4().hex[:8]}"),
            stage=payload.get("stage", stage.value),
            question=payload.get("question", ""),
            background=payload.get("background", ""),
            options=payload.get("options", []),
            recommended_option=payload.get("recommended_option"),
            deadline=payload.get("deadline"),
        )
        # Pre-register so the UI can fetch it.
        self.decision_manager._pending_decisions[decision.id] = decision
        state.add_decision_request(decision)

        yield {
            "type": "human_decision_required",
            "project_id": project_id,
            "stage": stage.value,
            "decision": payload,
            "message": payload.get("message", ""),
            "timestamp": datetime.now().isoformat(),
        }
        yield {"type": "pause", "reason": "human_decision"}

    async def _handle_conversation_continuation(
        self,
        project_id: str,
        stage: PipelineStage,
        result: AgentOutput,
        state: PipelineState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        payload = result.conversation_continuation or {}
        conv_id = payload.get("conversation_id", "")
        state.active_conversations[conv_id] = ConversationState(
            conversation_id=conv_id,
            agent_name=result.metadata.get("agent_name", stage.value),
            stage=stage.value,
            task_status="in_progress",
            continuation_count=payload.get("continuation_count", 0),
            max_continuations=payload.get("max_continuations", self.conversation_manager.max_continuations),
            continuation_reason=payload.get("reason", ""),
        )
        yield {
            "type": "conversation_continuation",
            "project_id": project_id,
            "stage": stage.value,
            "conversation": payload,
            "timestamp": datetime.now().isoformat(),
        }
        # The agent's execute() returned; we treat the conversation continuation
        # as non-blocking in this prototype. The UI can keep the conversation
        # open and the user can keep sending messages.

    async def submit_human_decision(
        self,
        project_id: str,
        decision_id: str,
        answer: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        state = self.active_pipelines.get(project_id)
        if not state:
            raise TaskOrchestrationError(f"Pipeline not found: {project_id}")
        request = self.decision_manager.get_decision(decision_id)
        if not request:
            raise TaskOrchestrationError(f"Decision not found: {decision_id}")
        if request.status == HumanDecisionStatus.PENDING:
            self.decision_manager.resolve_decision(decision_id, answer)
        elif request.status == HumanDecisionStatus.TIMEOUT:
            self.decision_manager.apply_timeout_fallback(decision_id)
        # Resume the pipeline - the next execute_pipeline picks up where we left off.
        async for event in self.execute_pipeline(project_id):
            yield event

    async def submit_conversation_message(
        self,
        project_id: str,
        conversation_id: str,
        content: str,
        role: str = "user",
    ) -> dict[str, Any]:
        """Append a user/agent message to a tracked conversation."""
        state = self.active_pipelines.get(project_id)
        if not state:
            raise TaskOrchestrationError(f"Pipeline not found: {project_id}")
        self.conversation_manager.append_message(conversation_id, role=role, content=content)
        if role == "user":
            self.conversation_manager.update_conversation(
                conversation_id, task_status="in_progress"
            )
        return self.conversation_manager.get_conversation(conversation_id).to_dict()  # type: ignore[union-attr]

    # =============================================================== context
    def _build_stage_context(
        self,
        stage: PipelineStage,
        full_context: dict[str, Any],
        state: PipelineState | None = None,
    ) -> dict[str, Any]:
        """Apply the per-stage history-access policy.

        Linear stages (requirements, architecture, frontend_design) receive
        the full project context.

        Loop stages (spec_development, code_testing, deployment) receive:

        * ``frontend_design`` artifact (the only required shared input)
        * the *immediately preceding* loop stage's artifact
        * **no** conversation history from requirements / architecture /
          frontend_design

        The intent is information isolation: the loop only knows about the
        frontend design contract and its own previous iteration's result.
        """
        policy = LOOP_STAGE_ACCESS.get(stage, "full")
        artifacts = full_context.get("artifacts", {}) or {}

        base_context: dict[str, Any] = {
            "project_id": full_context.get("project_id", ""),
            "name": full_context.get("name", ""),
            "description": full_context.get("description", ""),
            "current_stage": stage.value,
            "history_access_policy": policy,
        }

        if policy == "frontend_design_only":
            base_context["artifacts"] = {
                "frontend_design": artifacts.get("frontend_design", {}),
            }
        elif policy == "frontend_design_and_spec":
            base_context["artifacts"] = {
                "frontend_design": artifacts.get("frontend_design", {}),
                "spec_development": artifacts.get("spec_development", {}),
            }
        elif policy == "frontend_design_and_testing":
            base_context["artifacts"] = {
                "frontend_design": artifacts.get("frontend_design", {}),
                "code_testing": artifacts.get("code_testing", {}),
            }
        else:
            base_context["artifacts"] = dict(artifacts)

        # Loop iteration metadata
        if state is not None and stage in LOOP_STAGES:
            base_context["loop_iteration"] = state.loop_iteration
            base_context["max_loop_iterations"] = state.max_loop_iterations
            base_context["loop_history"] = [
                {
                    "iteration": r.iteration,
                    "test_passed": r.test_passed,
                    "deployment_validated": r.deployment_validated,
                    "exit_reason": r.exit_reason.value if r.exit_reason else None,
                    "notes": r.notes,
                }
                for r in state.loop_history
            ]
            # Forward the previous iteration's test report for context.
            test_artifact = artifacts.get("code_testing", {})
            if test_artifact and "content" in test_artifact:
                base_context.setdefault("previous_iteration", {})["test_report"] = test_artifact["content"]

        return base_context

    # ============================================================== helpers
    def _to_stage_result(
        self,
        stage: PipelineStage,
        agent_output: AgentOutput,
        loop_iteration: int = 1,
    ) -> StageResult:
        """Wrap an :class:`AgentOutput` in a :class:`StageResult` for the pipeline state."""
        return StageResult(
            stage=stage,
            success=agent_output.success,
            output=agent_output.result,
            files=agent_output.files,
            error=agent_output.error,
            started_at=agent_output.completed_at,  # approximate; sub-classes may refine
            completed_at=agent_output.completed_at,
            duration_seconds=0.0,
            iteration_count=loop_iteration,
        )

    def _get_agent_for_stage(self, stage: PipelineStage) -> BaseSubAgent:
        # Local import avoids a circular dependency with the agents package.
        from deerflow.devflow.agents import get_agent_class

        cls = get_agent_class(stage.value)
        if cls is None:
            raise TaskOrchestrationError(f"No agent registered for stage {stage.value}")
        return cls()

    def _is_test_report_green(self, content: str) -> bool:
        lowered = (content or "").lower()
        if not lowered:
            return False
        failed = "failed" in lowered or "error" in lowered or "traceback" in lowered
        passed_marker = "all tests passed" in lowered or "0 failed" in lowered or "tests: 0 failed" in lowered
        if failed and not passed_marker:
            return False
        if "coverage" in lowered:
            # Look for the first coverage percentage in the report.
            import re

            m = re.search(r"(?:line[- ]?coverage|coverage)[^\d]*(\d{1,3})\s*%", lowered)
            if m and int(m.group(1)) < 80:
                return False
        return passed_marker or ("passed" in lowered and not failed)

    def _is_deployment_valid(self, content: str) -> bool:
        lowered = (content or "").lower()
        if not lowered:
            return False
        bad = "deployment_invalid" in lowered or "deploy_failed" in lowered
        if bad:
            return False
        ok = (
            "successfully deployed" in lowered
            or "deployment_validated" in lowered
            or "deployment ok" in lowered
        )
        return ok or not bad

    # ============================================================== queries
    async def get_pipeline_status(self, project_id: str) -> PipelineState | None:
        state = self.active_pipelines.get(project_id)
        if not state:
            project = await self.memory.get_project(project_id)
            if not project:
                return None
            state = PipelineState(
                project_id=project_id,
                name=project.name,
                description=project.description,
                current_stage=PipelineStage(project.current_stage),
            )
            for stage_name in [s.value for s in PipelineStage]:
                artifact = await self.memory.get_stage_artifact(project_id, stage_name)
                if artifact:
                    state.completed_stages.append(
                        StageResult(
                            stage=PipelineStage(stage_name),
                            success=True,
                            output=artifact.content,
                            files=artifact.files,
                            completed_at=artifact.created_at,
                        )
                    )
            self.active_pipelines[project_id] = state
        return state

    async def get_all_projects(self) -> list[dict[str, Any]]:
        return [state.to_dict() for state in self.active_pipelines.values()]

    async def get_pending_decisions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        if project_id is not None:
            state = self.active_pipelines.get(project_id)
            if not state:
                return []
            return [
                self.decision_manager.format_decision_payload(d)
                for d in state.pending_decisions
                if d.status == HumanDecisionStatus.PENDING
            ]
        return [
            self.decision_manager.format_decision_payload(d)
            for d in self.decision_manager.get_pending_decisions()
        ]

    # =====================================================================
    # Chat mode - persistent multi-turn conversation with a single agent.
    #
    # The user can start a chat session with any registered agent, give it
    # a message, and the agent responds as if it were a chat assistant. The
    # session has its own message history; pipeline state is not affected.
    # The agent still respects its ``history_access_policy`` (so a chat
    # with ``spec_development`` will not see requirements/architecture
    # content - it sees only the frontend_design artifact plus the chat
    # history).
    # =====================================================================

    async def start_chat_session(
        self,
        project_id: str,
        agent_name: str,
        description: str = "",
    ) -> ChatSession:
        """Start a new chat session with the given agent."""
        from deerflow.devflow.agents import get_agent_class

        if get_agent_class(agent_name) is None:
            raise TaskOrchestrationError(f"Unknown agent: {agent_name}")
        # Resolve the agent's declared history_access policy from its config.
        scope = self.skill_loader.load_agent_scope(agent_name)
        history_access = scope.history_access or "full"

        # If the project doesn't exist in memory yet (the user may be
        # starting a brand-new project for this chat), create it and
        # adopt the project_id that the memory service returns. The
        # session is then bound to the canonical project_id so that
        # subsequent calls to ``chat_with_agent`` find the project.
        project = await self.memory.get_project(project_id)
        if not project:
            new_project = await self.memory.create_project(
                name=description or f"Chat with {agent_name}",
                description=description,
            )
            project_id = new_project.project_id

        session = self.chat_manager.start_session(
            project_id=project_id,
            agent_name=agent_name,
            description=description,
            history_access=history_access,
        )
        return session

    async def chat_with_agent(
        self,
        session_id: str,
        user_message: str,
    ) -> dict[str, Any]:
        """Send a message to the agent bound to ``session_id``.

        Returns a dict with the agent's textual reply, optional
        ``human_decision`` / ``conversation_continuation`` signals, and
        the updated session snapshot.
        """
        from deerflow.devflow.agents import get_agent_class

        session = self.chat_manager.get_session(session_id)
        if not session:
            raise TaskOrchestrationError(f"Chat session not found: {session_id}")
        if session.status != "active":
            raise TaskOrchestrationError(
                f"Chat session {session_id} is not active (status={session.status})"
            )

        agent_cls = get_agent_class(session.agent_name)
        if agent_cls is None:
            raise TaskOrchestrationError(f"Unknown agent: {session.agent_name}")
        agent = agent_cls()

        # 1) Persist the user message.
        self.chat_manager.append_message(session_id, role="user", content=user_message)

        # 2) Build the filtered context: project memory + chat history.
        full_context = await self.memory.get_project_context(session.project_id)
        chat_context = self._build_chat_context(
            session=session,
            full_context=full_context,
            user_message=user_message,
        )

        # 3) Drive the agent.
        agent_input = AgentInput(
            task=user_message,
            context=chat_context,
            previous_artifacts=chat_context.get("artifacts", {}),
            allowed_stages=[session.agent_name],
            trace_id=f"chat-{session_id}-{uuid.uuid4().hex[:6]}",
        )
        try:
            agent_output = await agent.execute(agent_input)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat agent %s failed: %s", session.agent_name, exc)
            agent_output = AgentOutput(
                result=f"Agent error: {exc}",
                success=False,
                error=str(exc),
            )

        # 4) Persist the agent's reply (and any human-interaction signals).
        self.chat_manager.append_message(
            session_id,
            role="agent",
            content=agent_output.result,
            metadata=agent_output.metadata,
            human_decision=agent_output.human_decision,
            conversation_continuation=agent_output.conversation_continuation,
        )

        return {
            "session": session.to_dict(),
            "reply": {
                "content": agent_output.result,
                "files": agent_output.files,
                "success": agent_output.success,
                "error": agent_output.error,
                "metadata": agent_output.metadata,
            },
            "human_decision": agent_output.human_decision,
            "conversation_continuation": agent_output.conversation_continuation,
        }

    async def close_chat_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.chat_manager.close_session(session_id)
        return session.to_dict() if session else None

    async def reopen_chat_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.chat_manager.reopen_session(session_id)
        return session.to_dict() if session else None

    async def list_chat_sessions(
        self,
        project_id: str | None = None,
        only_active: bool = True,
    ) -> list[dict[str, Any]]:
        if only_active:
            return [s.to_dict() for s in self.chat_manager.list_active_sessions(project_id=project_id)]
        return [s.to_dict() for s in self.chat_manager.list_sessions(project_id=project_id)]

    async def get_chat_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.chat_manager.get_session(session_id)
        if not session:
            return None
        return {
            "session": session.to_dict(),
            "messages": [m.content for m in session.messages],
            "history": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "metadata": m.metadata,
                    "human_decision": m.human_decision,
                    "conversation_continuation": m.conversation_continuation,
                }
                for m in session.messages
            ],
        }

    def _build_chat_context(
        self,
        session: ChatSession,
        full_context: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        """Build the context for a chat turn.

        The agent receives:

        * the project metadata
        * the artifacts filtered by its declared ``history_access`` policy
        * the chat history (so it remembers prior turns)
        * the user's current message
        """
        artifacts = full_context.get("artifacts", {}) or {}
        policy = session.history_access

        if policy == "frontend_design_only":
            visible_artifacts = {"frontend_design": artifacts.get("frontend_design", {})}
        elif policy == "frontend_design_and_spec":
            visible_artifacts = {
                "frontend_design": artifacts.get("frontend_design", {}),
                "spec_development": artifacts.get("spec_development", {}),
            }
        elif policy == "frontend_design_and_testing":
            visible_artifacts = {
                "frontend_design": artifacts.get("frontend_design", {}),
                "code_testing": artifacts.get("code_testing", {}),
            }
        else:
            visible_artifacts = dict(artifacts)

        chat_history = [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in session.messages[-30:]  # keep the most recent 30 messages
        ]

        return {
            "project_id": full_context.get("project_id", session.project_id),
            "name": full_context.get("name", ""),
            "description": full_context.get("description", ""),
            "current_stage": session.agent_name,
            "history_access_policy": policy,
            "mode": "chat",
            "session_id": session.session_id,
            "chat_history": chat_history,
            "artifacts": visible_artifacts,
        }
