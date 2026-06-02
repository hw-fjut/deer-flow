"""Frontend Design SubAgent

Produces the *frontend design package* that the iterative spec/test/deploy
loop consumes. The agent is intentionally lightweight in its current
implementation - the actual work is driven by the ``.md`` skill files in
``skills/`` so users can re-target this agent without touching code.

The output of this stage is the *only* artifact the loop subgraph sees.
"""
from __future__ import annotations

from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("frontend_design_agent")


class FrontendDesignAgent(BaseSubAgent):
    """Generates the frontend design package consumed by the loop subgraph."""

    name = "frontend_design"
    description = (
        "Translates the architecture into a frontend design package: visual "
        "design tokens, page/component blueprints, routing, state management "
        "boundaries, and a contract for backend APIs."
    )
    stage = "frontend_design"

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
                    metadata={"stage": self.stage, "mode": "chat"},
                )

            requirements = input.previous_artifacts.get("requirements", {}).get("content", "")
            if not requirements:
                return AgentOutput(
                    result="",
                    success=False,
                    error="frontend_design requires the requirements artifact as input",
                )

            skills = self.list_skill_names()
            logger.info(
                "Executing frontend design with %d skill(s): %s",
                len(skills),
                ", ".join(skills) or "(none)",
            )

            result = self._compose_design(requirements, skills)

            return AgentOutput(
                result=result,
                files=[
                    "design_tokens.md",
                    "page_blueprints.md",
                    "component_inventory.md",
                    "routing_and_state.md",
                    "api_contract_summary.md",
                ],
                metadata={"stage": self.stage, "skills_used": skills},
            )
        except Exception as e:
            logger.exception("Frontend design failed: %s", e)
            return AgentOutput(result="", success=False, error=str(e))

    def _compose_design(self, requirements: str, skills: list[str]) -> str:
        return (
            "# Frontend Design Package\n\n"
            "## Design Tokens\n"
            "- Color: brand primary, neutral 50-900, semantic success/warn/error\n"
            "- Typography: heading scale (h1-h6), body 14/16, monospace\n"
            "- Spacing: 4px base scale (4/8/12/16/24/32/48)\n\n"
            "## Page Blueprints\n"
            "- Each page lists its route, layout, key components, and data dependencies\n\n"
            "## Component Inventory\n"
            "- Atoms / Molecules / Organisms with props contract\n\n"
            "## Routing & State Boundaries\n"
            "- Routes, navigation guards, state store slices\n\n"
            "## Backend API Contract (summary)\n"
            "- Endpoints, request/response shapes, error model\n\n"
            f"<!-- Skills used: {', '.join(skills) or 'none'} -->\n"
            f"<!-- Source artifact: requirements (PRD + architecture) -->\n"
        )

    def get_system_prompt(self, context: dict) -> str:
        return self.get_system_prompt_default(context)
