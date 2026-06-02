"""Base agent definitions.

Every sub-agent in DevFlow implements :class:`BaseSubAgent`. The class wires
together three orthogonal concerns:

* **Skill scope** - which ``.md`` skill files the agent can load. The scope
  is defined per-agent and reloaded at runtime from disk, so editing a
  ``.md`` file is enough to customise behaviour.
* **History access** - the orchestrator passes a curated ``AgentInput`` whose
  ``context`` only contains artifacts the agent is allowed to see. The
  default access policy is *isolated* (frontend_design + previous loop
  stage only); the orchestrator widens the context for the linear head
  stages.
* **Human interaction hooks** - ``request_human_decision`` and
  ``request_conversation_continuation`` are convenience helpers that build
  the standardized payloads and yield them to the orchestrator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from deerflow.devflow.common.conversation_state import (
    ConversationStateManager,
    ConversationTrigger,
)
from deerflow.devflow.common.human_decision import HumanDecisionManager
from deerflow.devflow.common.logging import setup_logger
from deerflow.devflow.common.skill_config import (
    AgentSkillScope,
    SkillDefinition,
    get_skill_loader,
)
# NOTE: imports above go through specific submodules rather than
# ``deerflow.devflow.common`` to avoid a circular import via
# ``common.__init__`` -> ``main_agent.orchestrator``.


@dataclass
class AgentInput:
    """Input passed to a sub-agent.

    Attributes:
        task: Human-readable description of the task.
        context: Curated context - already filtered by the orchestrator to
            respect the agent's history-access policy.
        previous_artifacts: Map of ``stage -> {name, content, files, ...}``.
        allowed_stages: Pipeline stages this agent is allowed to run for.
    """

    task: str
    context: dict[str, Any] = field(default_factory=dict)
    previous_artifacts: dict[str, Any] = field(default_factory=dict)
    allowed_stages: list[str] = field(default_factory=list)
    trace_id: str = ""


@dataclass
class AgentOutput:
    """Output of a sub-agent execution.

    The ``human_decision`` and ``conversation_continuation`` fields let an
    agent surface mid-task user interactions back to the orchestrator
    without terminating itself.
    """

    result: str
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None
    completed_at: datetime = field(default_factory=datetime.now)

    # Optional human-interaction signals
    human_decision: dict[str, Any] | None = None
    conversation_continuation: dict[str, Any] | None = None
    partial: bool = False


class BaseSubAgent(ABC):
    """Base class for DevFlow sub-agents.

    Sub-classes should set the class-level ``name`` / ``description`` /
    ``stage`` attributes, and implement :meth:`execute` and
    :meth:`get_system_prompt`.
    """

    name: str = ""
    description: str = ""
    stage: str = ""

    def __init__(self, skill_loader=None):
        self.logger = setup_logger(f"agent.{self.name or self.__class__.__name__}")
        self._skill_loader = skill_loader or get_skill_loader()
        self._skill_scope: AgentSkillScope | None = None

    # ----------------------------------------------------------------- skills
    @property
    def skill_scope(self) -> AgentSkillScope:
        if self._skill_scope is None:
            self._skill_scope = self._skill_loader.load_agent_scope(self.name or self.stage)
        return self._skill_scope

    def reload_skills(self) -> AgentSkillScope:
        self._skill_scope = self._skill_loader.reload_agent(self.name or self.stage)
        return self._skill_scope

    def get_skill(self, skill_name: str) -> SkillDefinition | None:
        return self._skill_loader.load_skill(self.name or self.stage, skill_name)

    def list_skill_names(self) -> list[str]:
        return self.skill_scope.skill_names()

    def render_skill_prompt(self) -> str:
        """Render the active skills as a system-prompt fragment."""
        scope = self.skill_scope
        if not scope.skills:
            return ""
        lines = ["## Active Skills (loaded from .md skill files)", ""]
        for skill in scope.skills:
            lines.append(f"### Skill: {skill.name}")
            if skill.description:
                lines.append(f"Description: {skill.description}")
            if skill.tools:
                lines.append(f"Tools: {', '.join(skill.tools)}")
            if skill.constraints:
                lines.append("Constraints:")
                for c in skill.constraints:
                    lines.append(f"- {c}")
            if skill.output_format:
                lines.append(f"Output Format: {skill.output_format}")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------ abstract API
    @abstractmethod
    async def execute(self, input: AgentInput) -> AgentOutput:
        """Execute the agent task. Must be implemented by every sub-class."""

    @abstractmethod
    def get_system_prompt(self, context: dict[str, Any]) -> str:
        """Return the system prompt for this agent.

        The base implementation returns ``description`` plus the rendered
        skill block. Sub-classes may extend or override.
        """

    # -------------------------------------------------------------- validation
    def validate_input(self, input: AgentInput) -> None:
        if not input.task:
            raise ValueError("Task cannot be empty")

    def format_context(self, context: dict[str, Any]) -> str:
        lines = ["## Project Context", ""]
        if "name" in context:
            lines.append(f"Project Name: {context['name']}")
        if "description" in context:
            lines.append(f"Description: {context['description']}")
        if context.get("mode") == "chat":
            lines.append("Mode: **CHAT** (the user is talking directly to you; respond conversationally)")
        artifacts = context.get("artifacts", {})
        if artifacts:
            lines += ["", "## Available Artifacts (filtered by access policy)", ""]
            for stage, artifact in artifacts.items():
                lines.append(f"### {stage}")
                lines.append(f"Name: {artifact.get('name', 'N/A')}")
                content = artifact.get("content", "N/A")
                lines.append(f"Content (excerpt): {content[:500]}{'...' if len(content) > 500 else ''}")
                lines.append("")
        history = context.get("conversation_history", [])
        if history:
            lines += ["", "## Recent Conversation History", ""]
            for msg in history[-5:]:
                lines.append(f"- [{msg.get('role', '?')}] {str(msg.get('content', ''))[:200]}")
        chat_history = context.get("chat_history", [])
        if chat_history:
            lines += ["", "## Chat History (current session)", ""]
            for msg in chat_history[-20:]:
                role = msg.get("role", "?")
                content = str(msg.get("content", ""))[:500]
                lines.append(f"- [{role}] {content}")
        return "\n".join(lines)

    def render_chat_response(
        self,
        task: str,
        chat_history: list[dict[str, Any]] | None = None,
        artifacts: dict[str, Any] | None = None,
    ) -> str:
        """Build a deterministic skeleton reply for the chat mode.

        Real LLM-backed sub-classes will override ``execute`` and ignore
        this helper; the skeleton implementation is a safe fallback that
        lets the rest of the chat pipeline be exercised end-to-end.
        """
        turns = len(chat_history or [])
        artifact_names = list((artifacts or {}).keys())
        return (
            f"#{ self.name or 'agent' } - chat reply\n\n"
            f"You said: {task}\n\n"
            f"- Turn: {turns}\n"
            f"- Visible artifacts: {', '.join(artifact_names) or '(none)'}\n"
            f"- Policy: {self.skill_scope.history_access}\n"
        )

    # ------------------------------------------------------ human interaction
    def request_human_decision(
        self,
        manager: HumanDecisionManager,
        *,
        question: str,
        background: str,
        options: list[dict[str, str]],
        recommended_option: str | None = None,
        impact: str = "",
        related_artifacts: list[str] | None = None,
        timeout_hours: int | None = None,
    ) -> AgentOutput:
        """Build a Type-1 human decision request from inside ``execute()``.

        The returned :class:`AgentOutput` carries the decision payload in
        ``output.human_decision``; the orchestrator pauses the pipeline when
        it sees that field.
        """
        request = manager.create_decision_request(
            stage=self.stage,
            question=question,
            background=background,
            options=options,
            recommended_option=recommended_option,
            timeout_hours=timeout_hours,
            impact=impact,
            related_artifacts=related_artifacts,
        )
        payload = manager.format_decision_payload(request)
        return AgentOutput(
            result=manager.format_decision_message(request),
            success=True,
            metadata={"pause_reason": "human_decision", "decision_id": request.id},
            human_decision=payload,
        )

    def request_conversation_continuation(
        self,
        manager: ConversationStateManager,
        *,
        conversation_id: str,
        question: str,
        reason: str,
        trigger: ConversationTrigger = ConversationTrigger.CLARIFICATION,
    ) -> AgentOutput:
        """Build a Type-2 conversation continuation request."""
        allowed, state = manager.request_continuation(
            conversation_id=conversation_id,
            reason=reason,
            trigger=trigger,
        )
        if not allowed:
            return AgentOutput(
                result=(
                    "Conversation continuation exhausted - escalating to human decision."
                ),
                success=False,
                error="conversation_exhausted",
                metadata={
                    "pause_reason": "conversation_exhausted",
                    "conversation_id": conversation_id,
                },
            )
        manager.append_message(conversation_id, role="agent", content=question)
        return AgentOutput(
            result=question,
            success=True,
            metadata={
                "pause_reason": "conversation_continuation",
                "conversation_id": conversation_id,
                "continuation_count": state.continuation_count if state else 0,
            },
            conversation_continuation={
                "conversation_id": conversation_id,
                "question": question,
                "reason": reason,
                "trigger": trigger.value,
                "continuation_count": state.continuation_count if state else 0,
                "max_continuations": state.max_continuations if state else 0,
            },
        )

    def get_system_prompt_default(self, context: dict[str, Any]) -> str:
        """Default system prompt combining description, context, and skills."""
        parts = [self.description or f"You are the {self.name} sub-agent."]
        parts.append(self.render_skill_prompt())
        parts.append(self.format_context(context))
        return "\n\n".join(p for p in parts if p)
