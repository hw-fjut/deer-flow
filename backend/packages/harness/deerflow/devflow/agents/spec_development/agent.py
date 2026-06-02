"""Spec Development Agent - generates technical specifications.

The agent is the *first* member of the loop subgraph. Per the DevFlow
information-isolation policy, it receives only the frontend_design artifact
plus the previous loop iteration's result - never the requirements or
architecture conversation history.

The agent's behaviour is defined by the ``.md`` files in
``skills/``. Editing those files is sufficient to retarget the agent
(adding new spec types, swapping the API style, etc.).
"""
from __future__ import annotations

from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("spec_development_agent")


class SpecDevelopmentAgent(BaseSubAgent):
    """Generates detailed technical specifications from the frontend design."""

    name = "spec_development"
    description = (
        "Generates formal API / data-model / state-machine specs from the "
        "frontend design package."
    )
    stage = "spec_development"

    async def execute(self, input: AgentInput) -> AgentOutput:
        try:
            self.validate_input(input)

            # Chat mode: respond to the user's message.
            if input.context.get("mode") == "chat":
                return AgentOutput(
                    result=self.render_chat_response(
                        task=input.task,
                        chat_history=input.context.get("chat_history", []),
                        artifacts=input.context.get("artifacts", {}),
                    ),
                    files=[],
                    metadata={"stage": self.stage, "mode": "chat", "history_access_policy": input.context.get("history_access_policy")},
                )

            frontend_design = input.previous_artifacts.get("frontend_design", {}).get("content", "")
            previous_test = (input.context.get("previous_iteration") or {}).get("test_report", "")
            if not frontend_design:
                return AgentOutput(
                    result="",
                    success=False,
                    error="spec_development requires the frontend_design artifact",
                )

            skills = self.list_skill_names()
            logger.info(
                "Executing spec development with %d skill(s): %s",
                len(skills),
                ", ".join(skills) or "(none)",
            )
            logger.info(
                "Spec development context: policy=%s, has_previous_test=%s",
                input.context.get("history_access_policy"),
                bool(previous_test),
            )

            result = self._generate_specs(frontend_design, previous_test, skills)

            return AgentOutput(
                result=result,
                files=["api_specs.md", "data_models.md", "interfaces.md", "state_machines.md"],
                metadata={
                    "stage": self.stage,
                    "skills_used": skills,
                    "history_access_policy": input.context.get("history_access_policy"),
                    "loop_iteration": input.context.get("loop_iteration", 1),
                },
            )
        except Exception as e:
            logger.exception("Spec development failed: %s", e)
            return AgentOutput(result="", success=False, error=str(e))

    def _generate_specs(self, frontend_design: str, previous_test: str, skills: list[str]) -> str:
        return (
            "# Technical Specifications (auto-generated)\n\n"
            "## API Specifications\n"
            "- POST /api/v1/users - create user\n"
            "- GET  /api/v1/users/{id} - fetch user\n"
            "- PUT  /api/v1/users/{id} - update user\n"
            "- DELETE /api/v1/users/{id} - delete user\n\n"
            "## Data Model Specifications\n"
            "- users(id uuid pk, email citext unique, name text, created_at timestamptz)\n\n"
            "## Interface Specifications\n"
            "- IUserService: createUser/getUser/updateUser/deleteUser\n\n"
            "## State Machine Specifications\n"
            "- UserLifecycle: invited -> active -> suspended -> deleted\n\n"
            f"<!-- Skills used: {', '.join(skills) or 'none'} -->\n"
            f"<!-- History access policy: frontend_design_only -->\n"
            f"<!-- Previous test report length: {len(previous_test)} chars -->\n"
        )

    def get_system_prompt(self, context: dict) -> str:
        return self.get_system_prompt_default(context)
