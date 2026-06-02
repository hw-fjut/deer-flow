"""Requirements Analysis Agent - produces a combined PRD + architecture document.

Architecture is intentionally folded into the same agent because the two
concerns (what to build + how to build it) are too tightly coupled to be
worth splitting into separate pipeline stages. The agent's output contains
both the requirements (MoSCoW priority, acceptance criteria) and the
architecture (stack, components, API style) so the downstream
``frontend_design`` agent can consume a single artifact.
"""
from __future__ import annotations

from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("requirements_agent")


class RequirementsAgent(BaseSubAgent):
    """Analyzes the user request and produces a combined PRD + architecture document."""

    name = "requirements"
    description = (
        "Analyzes the user request and produces a combined PRD + architecture "
        "document. The frontend_design agent consumes this artifact."
    )
    stage = "requirements"

    async def execute(self, input: AgentInput) -> AgentOutput:
        try:
            self.validate_input(input)
            skills = self.list_skill_names()
            logger.info("Executing requirements analysis with %d skill(s): %s", len(skills), ", ".join(skills) or "(none)")
            # Chat mode: respond to the user's message using the same context.
            if input.context.get("mode") == "chat":
                return AgentOutput(
                    result=self.render_chat_response(
                        task=input.task,
                        chat_history=input.context.get("chat_history", []),
                        artifacts=input.context.get("artifacts", {}),
                    ),
                    files=[],
                    metadata={"stage": self.stage, "mode": "chat", "skills_used": skills},
                )
            result = self._build_requirements_and_architecture(input.task, skills)
            return AgentOutput(
                result=result,
                files=["PRD.md", "ARCHITECTURE.md"],
                metadata={"stage": self.stage, "skills_used": skills},
            )
        except Exception as e:
            logger.exception("Requirements analysis failed: %s", e)
            return AgentOutput(result="", success=False, error=str(e))

    def _build_requirements_and_architecture(self, task: str, skills: list[str]) -> str:
        return (
            "# Requirements & Architecture\n\n"
            "## 1. Executive Summary\n"
            f"{task}\n\n"
            "## 2. Requirements (PRD)\n\n"
            "### 2.1 User Personas\n"
            "- End users\n"
            "- Administrators\n\n"
            "### 2.2 Functional Requirements\n"
            "- Core feature set as described in the request\n\n"
            "### 2.3 Non-Functional Requirements\n"
            "- Performance: < 2s p95\n"
            "- Availability: 99.9%\n\n"
            "### 2.4 Priority Matrix (MoSCoW)\n"
            "- Must / Should / Could / Won't\n\n"
            "### 2.5 Acceptance Criteria\n"
            "- Each user story has a measurable acceptance test\n\n"
            "## 3. Architecture\n\n"
            "### 3.1 System Overview\n"
            "- Service-oriented architecture\n\n"
            "### 3.2 Technology Stack\n"
            "- Backend: Python / FastAPI\n"
            "- Frontend: React\n"
            "- DB: PostgreSQL\n\n"
            "### 3.3 Components\n"
            "- API Gateway, Auth Service, Domain Services, Workers\n\n"
            "### 3.4 API Design\n"
            "- REST + OpenAPI 3.1\n\n"
            "### 3.5 Deployment Topology\n"
            "- Docker + Kubernetes\n\n"
            f"<!-- Skills used: {', '.join(skills) or 'none'} -->\n"
        )

    def get_system_prompt(self, context: dict) -> str:
        return self.get_system_prompt_default(context)
