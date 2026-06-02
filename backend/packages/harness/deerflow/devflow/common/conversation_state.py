"""Non-decision conversation state tracking.

This module implements *Type-2 human interaction* in DevFlow: when a sub-agent
needs additional information or wants to keep iterating with the user without
making a hard decision, it starts a *conversation*. The conversation has:

* a ``task_status`` (in_progress / completed / blocked)
* a continuation budget (``max_continuations``)
* a per-conversation history
* an automatic escalation path to a Type-1 human decision request when the
  budget is exhausted and the task is still in progress.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("conversation_state")


class ConversationTrigger(str, Enum):
    """What triggered the conversation continuation."""

    CLARIFICATION = "clarification"
    ADDITIONAL_CONTEXT = "additional_context"
    CONFIRM_APPROACH = "confirm_approach"
    INCOMPLETE_TASK = "incomplete_task"
    PARTIAL_OUTPUT_REVIEW = "partial_output_review"
    OTHER = "other"


@dataclass
class ConversationMessage:
    """A single message inside an agent <-> user conversation."""

    role: str  # "user" | "agent" | "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationState:
    """Conversation state tracking (Type-2 human interaction)."""

    conversation_id: str
    agent_name: str
    stage: str
    task_status: str = "in_progress"  # in_progress | completed | blocked
    pending_actions: list[str] = field(default_factory=list)
    continuation_reason: str = ""
    trigger: ConversationTrigger = ConversationTrigger.CLARIFICATION
    max_continuations: int = 3
    continuation_count: int = 0
    history: list[ConversationMessage] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
    escalated_decision_id: str | None = None

    def can_continue(self) -> bool:
        return self.continuation_count < self.max_continuations

    def increment_continuation(self) -> None:
        self.continuation_count += 1
        self.last_updated = datetime.now()

    def is_exhausted(self) -> bool:
        return self.continuation_count >= self.max_continuations

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "agent_name": self.agent_name,
            "stage": self.stage,
            "task_status": self.task_status,
            "pending_actions": self.pending_actions,
            "continuation_reason": self.continuation_reason,
            "trigger": self.trigger.value,
            "max_continuations": self.max_continuations,
            "continuation_count": self.continuation_count,
            "last_updated": self.last_updated.isoformat(),
            "escalated_decision_id": self.escalated_decision_id,
            "history_length": len(self.history),
        }


class ConversationStateManager:
    """Track and manage the lifecycle of Type-2 conversations."""

    def __init__(self, max_continuations: int = 3):
        self.max_continuations = max_continuations
        self._active_conversations: dict[str, ConversationState] = {}

    # ------------------------------------------------------------------ create
    def start_conversation(
        self,
        agent_name: str,
        stage: str,
        task_status: str = "in_progress",
        pending_actions: list[str] | None = None,
        trigger: ConversationTrigger = ConversationTrigger.CLARIFICATION,
        reason: str = "",
    ) -> str:
        conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
        state = ConversationState(
            conversation_id=conversation_id,
            agent_name=agent_name,
            stage=stage,
            task_status=task_status,
            pending_actions=pending_actions or [],
            trigger=trigger,
            continuation_reason=reason,
            max_continuations=self.max_continuations,
        )
        self._active_conversations[conversation_id] = state
        logger.info(
            "Started conversation %s for agent=%s stage=%s trigger=%s",
            conversation_id,
            agent_name,
            stage,
            trigger.value,
        )
        return conversation_id

    # ------------------------------------------------------------------ update
    def update_conversation(
        self,
        conversation_id: str,
        task_status: str | None = None,
        pending_actions: list[str] | None = None,
        continuation_reason: str = "",
    ) -> bool:
        state = self._active_conversations.get(conversation_id)
        if not state:
            logger.warning("Conversation not found: %s", conversation_id)
            return False
        if task_status:
            state.task_status = task_status
        if pending_actions is not None:
            state.pending_actions = pending_actions
        if continuation_reason:
            state.continuation_reason = continuation_reason
        state.last_updated = datetime.now()
        return True

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        state = self._active_conversations.get(conversation_id)
        if not state:
            return False
        state.history.append(
            ConversationMessage(role=role, content=content, metadata=metadata or {})
        )
        state.last_updated = datetime.now()
        return True

    # -------------------------------------------------------------- continuations
    def request_continuation(
        self,
        conversation_id: str,
        reason: str,
        trigger: ConversationTrigger | None = None,
    ) -> tuple[bool, ConversationState | None]:
        """Request another turn in the conversation.

        Returns ``(allowed, state)``. When ``allowed`` is ``False`` the caller
        *must* escalate to a Type-1 human decision.
        """
        state = self._active_conversations.get(conversation_id)
        if not state:
            logger.warning("Conversation not found: %s", conversation_id)
            return False, None
        if not state.can_continue():
            logger.warning(
                "Max continuations reached for %s (count=%d, max=%d)",
                conversation_id,
                state.continuation_count,
                state.max_continuations,
            )
            return False, state
        state.increment_continuation()
        state.continuation_reason = reason
        state.task_status = "in_progress"
        if trigger is not None:
            state.trigger = trigger
        logger.info(
            "Continuation %d/%d granted for %s reason=%s",
            state.continuation_count,
            state.max_continuations,
            conversation_id,
            reason,
        )
        return True, state

    def should_escalate(self, conversation_id: str) -> bool:
        """Whether the conversation must be escalated to a Type-1 decision."""
        state = self._active_conversations.get(conversation_id)
        if not state:
            return False
        return state.task_status == "in_progress" and state.is_exhausted()

    def mark_escalated(self, conversation_id: str, decision_id: str) -> None:
        state = self._active_conversations.get(conversation_id)
        if not state:
            return
        state.escalated_decision_id = decision_id
        state.task_status = "blocked"
        state.last_updated = datetime.now()
        logger.info("Conversation %s escalated to decision %s", conversation_id, decision_id)

    # ------------------------------------------------------------------ complete
    def complete_conversation(self, conversation_id: str) -> ConversationState | None:
        state = self._active_conversations.pop(conversation_id, None)
        if state:
            state.task_status = "completed"
            state.last_updated = datetime.now()
            logger.info("Completed conversation: %s", conversation_id)
        return state

    # --------------------------------------------------------------------- query
    def get_conversation(self, conversation_id: str) -> ConversationState | None:
        return self._active_conversations.get(conversation_id)

    def get_all_active(self) -> dict[str, ConversationState]:
        return dict(self._active_conversations)

    def get_history(self, conversation_id: str) -> list[ConversationMessage]:
        state = self._active_conversations.get(conversation_id)
        return list(state.history) if state else []


# =============================================================================
# Chat mode - persistent multi-turn conversation with a single agent.
#
# This is the *Type-3* interaction mode: the user picks a specific agent and
# talks to it directly, outside of any pipeline execution. Chat sessions
# are independent of pipeline runs and can co-exist with them.
# =============================================================================


@dataclass
class ChatMessage:
    """A single message inside a chat session."""

    role: str  # "user" | "agent" | "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    human_decision: dict[str, Any] | None = None
    conversation_continuation: dict[str, Any] | None = None


@dataclass
class ChatSession:
    """An independent, persistent multi-turn conversation with one specific agent."""

    session_id: str
    project_id: str
    agent_name: str
    history_access: str  # resolved from the agent's config
    description: str = ""
    status: str = "active"  # "active" | "closed"
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_activity = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "agent_name": self.agent_name,
            "history_access": self.history_access,
            "description": self.description,
            "status": self.status,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "metadata": self.metadata,
        }


class ChatSessionManager:
    """Manage the lifecycle of chat sessions.

    Chat sessions are *unlimited-turn* by default - there is no
    ``max_continuations`` and no automatic escalation. The user can ask
    the agent for a Type-1 decision or a Type-2 continuation at any
    time, and the agent can return the corresponding signals inside a
    normal chat reply.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    # ------------------------------------------------------------------ create
    def start_session(
        self,
        project_id: str,
        agent_name: str,
        description: str = "",
        history_access: str = "full",
    ) -> ChatSession:
        session_id = f"chat-{uuid.uuid4().hex[:8]}"
        session = ChatSession(
            session_id=session_id,
            project_id=project_id,
            agent_name=agent_name,
            history_access=history_access,
            description=description,
        )
        self._sessions[session_id] = session
        logger.info(
            "Started chat session %s for agent=%s project=%s",
            session_id,
            agent_name,
            project_id,
        )
        return session

    # ------------------------------------------------------------------ update
    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        human_decision: dict[str, Any] | None = None,
        conversation_continuation: dict[str, Any] | None = None,
    ) -> ChatMessage | None:
        session = self._sessions.get(session_id)
        if not session:
            logger.warning("Chat session not found: %s", session_id)
            return None
        message = ChatMessage(
            role=role,
            content=content,
            metadata=metadata or {},
            human_decision=human_decision,
            conversation_continuation=conversation_continuation,
        )
        session.messages.append(message)
        session.touch()
        return message

    # ------------------------------------------------------------------ queries
    def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self, project_id: str | None = None) -> list[ChatSession]:
        if project_id is None:
            return list(self._sessions.values())
        return [s for s in self._sessions.values() if s.project_id == project_id]

    def list_active_sessions(self, project_id: str | None = None) -> list[ChatSession]:
        return [
            s
            for s in self.list_sessions(project_id=project_id)
            if s.status == "active"
        ]

    def get_history(self, session_id: str) -> list[ChatMessage]:
        session = self._sessions.get(session_id)
        return list(session.messages) if session else []

    # ----------------------------------------------------------------- close
    def close_session(self, session_id: str) -> ChatSession | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.status = "closed"
        session.touch()
        logger.info("Closed chat session: %s", session_id)
        return session

    def reopen_session(self, session_id: str) -> ChatSession | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.status = "active"
        session.touch()
        return session
