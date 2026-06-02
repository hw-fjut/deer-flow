"""Standardized human decision management.

Two human-interaction scenarios are supported:

1. **Human decision required** (this module) - the agent needs the user to
   pick between several well-defined options. The template always includes
   a *background*, a list of *options*, a *recommendation* and a
   *deadline*.

2. **Non-decision conversation continuation** (``conversation_state``) - the
   agent needs more information or wants to keep iterating. The conversation
   state is tracked automatically and escalates to a Type-1 decision when
   the configured continuation ceiling is exceeded.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from deerflow.devflow.common.logging import setup_logger
from deerflow.devflow.main_agent.state import HumanDecisionRequest, HumanDecisionStatus

logger = setup_logger("human_decision")


class HumanDecisionManager:
    """Manage the lifecycle of human decision requests in the pipeline."""

    def __init__(self, default_timeout_hours: int = 24):
        self.default_timeout_hours = default_timeout_hours
        self._pending_decisions: dict[str, HumanDecisionRequest] = {}

    # ----------------------------------------------------------------- create
    def create_decision_request(
        self,
        stage: str,
        question: str,
        background: str,
        options: list[dict[str, str]],
        recommended_option: str | None = None,
        timeout_hours: int | None = None,
        impact: str = "",
        related_artifacts: list[str] | None = None,
    ) -> HumanDecisionRequest:
        """Create a fully populated decision request.

        Args:
            stage: Current pipeline stage.
            question: The single, well-formed question being asked.
            background: Full context for the user to make an informed decision.
            options: ``[{label, description, recommendation}]`` - 2 to 4 options.
            recommended_option: Label of the recommended option (must match one
                of ``options[].label``).
            timeout_hours: Decision timeout in hours.
            impact: "what changes if the user picks the recommended option".
            related_artifacts: Names of artifacts that will be affected.
        """
        decision_id = f"dec-{uuid.uuid4().hex[:8]}"
        timeout = timeout_hours or self.default_timeout_hours
        deadline = (datetime.now() + timedelta(hours=timeout)).isoformat()

        # Inject impact / related_artifacts into the option text when present.
        enriched_options: list[dict[str, str]] = []
        for opt in options:
            enriched = dict(opt)
            if impact and "impact" not in enriched:
                enriched["impact"] = impact
            enriched_options.append(enriched)

        request = HumanDecisionRequest(
            id=decision_id,
            stage=stage,
            question=question,
            background=background,
            options=enriched_options,
            recommended_option=recommended_option,
            deadline=deadline,
        )
        # Stash extra metadata for the UI layer.
        request.__dict__["impact"] = impact
        request.__dict__["related_artifacts"] = related_artifacts or []

        self._pending_decisions[decision_id] = request
        logger.info(
            "Created decision request %s for stage=%s question=%s",
            decision_id,
            stage,
            question[:80],
        )
        return request

    # ----------------------------------------------------------------- format
    def format_decision_message(self, request: HumanDecisionRequest) -> str:
        """Format the decision request as a markdown document.

        The output is suitable for direct rendering in the chat UI and for
        being used as the body of an SSE ``human_decision_required`` event.
        """
        impact = request.__dict__.get("impact", "")
        related = request.__dict__.get("related_artifacts", []) or []

        lines = [
            "## Human Decision Required",
            "",
            f"**Stage:** {request.stage}",
            f"**Question:** {request.question}",
            f"**Deadline:** {request.deadline}",
            f"**Decision ID:** `{request.id}`",
            "",
            "### Background",
            request.background,
        ]
        if impact:
            lines += ["", "### Impact of the Decision", impact]
        if related:
            lines += ["", "### Related Artifacts", ", ".join(f"`{a}`" for a in related)]
        lines += ["", "### Options", ""]
        for opt in request.options:
            marker = " **[RECOMMENDED]**" if opt.get("label") == request.recommended_option else ""
            lines.append(f"- **{opt.get('label', '?')}**{marker}")
            if opt.get("description"):
                lines.append(f"  {opt['description']}")
            if opt.get("impact"):
                lines.append(f"  - impact: {opt['impact']}")
        if request.recommended_option:
            lines += [
                "",
                f"**Agent Recommendation:** {request.recommended_option}",
                "",
                "Reply with the option label to continue the pipeline.",
            ]
        return "\n".join(lines)

    def format_decision_payload(self, request: HumanDecisionRequest) -> dict[str, Any]:
        """Return a JSON-serializable payload for SSE / API consumption."""
        return {
            "id": request.id,
            "stage": request.stage,
            "question": request.question,
            "background": request.background,
            "options": request.options,
            "recommended_option": request.recommended_option,
            "deadline": request.deadline,
            "impact": request.__dict__.get("impact", ""),
            "related_artifacts": request.__dict__.get("related_artifacts", []),
            "status": request.status.value,
            "created_at": request.created_at.isoformat(),
            "message": self.format_decision_message(request),
        }

    # ----------------------------------------------------------------- resolve
    def resolve_decision(self, decision_id: str, answer: str) -> HumanDecisionRequest | None:
        request = self._pending_decisions.get(decision_id)
        if not request:
            logger.warning("Decision not found: %s", decision_id)
            return None

        # Validate the answer against the declared options.
        if request.options:
            valid_labels = {opt.get("label") for opt in request.options}
            if answer not in valid_labels:
                # Allow free-form answers but log a warning - the orchestrator
                # decides whether to accept or re-prompt.
                logger.info(
                    "Decision %s answered with free-form text %s (valid labels: %s)",
                    decision_id,
                    answer,
                    sorted(valid_labels),
                )

        request.answer = answer
        request.status = HumanDecisionStatus.ANSWERED
        request.answered_at = datetime.now()
        logger.info("Resolved decision %s with answer=%s", decision_id, answer)
        return request

    def cancel_decision(self, decision_id: str) -> HumanDecisionRequest | None:
        request = self._pending_decisions.get(decision_id)
        if not request:
            return None
        request.status = HumanDecisionStatus.CANCELLED
        return request

    def check_timeouts(self) -> list[HumanDecisionRequest]:
        timed_out: list[HumanDecisionRequest] = []
        now = datetime.now()
        for decision_id, request in list(self._pending_decisions.items()):
            if request.status != HumanDecisionStatus.PENDING:
                continue
            if request.deadline:
                deadline = datetime.fromisoformat(request.deadline)
                if now > deadline:
                    request.status = HumanDecisionStatus.TIMEOUT
                    timed_out.append(request)
                    logger.warning("Decision timed out: %s", decision_id)
        return timed_out

    def apply_timeout_fallback(self, decision_id: str) -> str | None:
        """Return the recommended option for a timed-out decision."""
        request = self._pending_decisions.get(decision_id)
        if not request or request.status != HumanDecisionStatus.TIMEOUT:
            return None
        if request.recommended_option:
            request.answer = request.recommended_option
            request.status = HumanDecisionStatus.ANSWERED
            request.answered_at = datetime.now()
        return request.answer

    # ------------------------------------------------------------------ query
    def get_pending_decisions(self) -> list[HumanDecisionRequest]:
        return [r for r in self._pending_decisions.values() if r.status == HumanDecisionStatus.PENDING]

    def get_decision(self, decision_id: str) -> HumanDecisionRequest | None:
        return self._pending_decisions.get(decision_id)

    def get_decision_history(self) -> list[HumanDecisionRequest]:
        return list(self._pending_decisions.values())
