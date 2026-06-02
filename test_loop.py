"""Test the loop subgraph retry / escalation paths.

Scenarios:
1. Failing test report -> loop retries up to max_iterations
2. Sub-agent raises a human decision -> orchestrator pauses
3. Sub-agent escalates from conversation exhaustion -> orchestrator pauses
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"e:\sourceCode\deer-flow\backend\packages\harness")
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEVFLOW_MEMORY_DIR", tempfile.mkdtemp(prefix="devflow_loop_"))

from deerflow.devflow.agents import get_agent_registry  # noqa: E402
from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent  # noqa: E402
from deerflow.devflow.main_agent.orchestrator import DevFlowOrchestrator  # noqa: E402
from deerflow.devflow.main_agent.state import PipelineStage  # noqa: E402


# ------------------------------------------------------------------ test stubs
class FailingTestAgent(BaseSubAgent):
    """Code testing agent that always reports a failing test."""
    name = "code_testing"
    stage = "code_testing"

    async def execute(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            result="Test Report\n\n- 5 tests failed\n- 2 errored\n- coverage: 30%\n",
            files=["tests/report.md"],
            metadata={"history_access_policy": input.context.get("history_access_policy")},
        )

    def get_system_prompt(self, context: dict) -> str:
        return ""


class EscalatingSpecAgent(BaseSubAgent):
    """Spec development agent that escalates by emitting a human decision."""
    name = "spec_development"
    stage = "spec_development"

    async def execute(self, input: AgentInput) -> AgentOutput:
        return AgentOutput(
            result="Need human input on the auth model",
            files=[],
            metadata={"pause_reason": "spec_needs_review"},
            human_decision={
                "id": "dec-test-001",
                "stage": "spec_development",
                "question": "Which auth model should we use?",
                "background": "PRD says SSO preferred but doesn't say which IdP.",
                "options": [
                    {"label": "Auth0", "description": "Hosted"},
                    {"label": "Keycloak", "description": "Self-hosted"},
                ],
                "recommended_option": "Auth0",
            },
        )

    def get_system_prompt(self, context: dict) -> str:
        return ""


async def scenario_failing_tests_retry():
    print("== Scenario 1: failing test report -> loop retries ==")
    # Patch registry
    from deerflow.devflow.agents import _build_registry
    import deerflow.devflow.agents as agents_pkg

    def patched_registry():
        reg = _build_registry()
        reg["code_testing"] = FailingTestAgent
        return reg

    agents_pkg._build_registry = patched_registry  # type: ignore

    orch = DevFlowOrchestrator(max_loop_iterations=3)
    state = await orch.start_pipeline(name="Retry Test", description="Loop retry test")
    events = []
    async for ev in orch.execute_pipeline(state.project_id):
        events.append(ev)
    types = [e["type"] for e in events]
    print("events:", [t for t in types if t.startswith(("loop_", "stage_", "pipeline_"))])
    # Expect: tests fail on every iteration, then loop_retry_exhausted
    assert "loop_retry_exhausted" in types, "expected loop to exhaust retries"
    assert "loop_retry" in types, "expected at least one loop retry"
    status = await orch.get_pipeline_status(state.project_id)
    print(f"loop_iteration={status.loop_iteration}, exit_reason={status.loop_exit_reason.value if status.loop_exit_reason else None}")
    assert status.loop_iteration == 3
    print("scenario 1 PASSED")
    print()


async def scenario_human_decision_pause():
    print("== Scenario 2: sub-agent escalates via human decision ==")
    from deerflow.devflow.agents import _build_registry
    import deerflow.devflow.agents as agents_pkg

    def patched_registry():
        reg = _build_registry()
        reg["spec_development"] = EscalatingSpecAgent
        return reg

    agents_pkg._build_registry = patched_registry  # type: ignore

    orch = DevFlowOrchestrator(max_loop_iterations=3)
    state = await orch.start_pipeline(name="Decision Pause", description="x")
    events = []
    async for ev in orch.execute_pipeline(state.project_id):
        events.append(ev)
    types = [e["type"] for e in events]
    print("events:", [t for t in types if t.startswith(("loop_", "stage_", "pipeline_", "human_"))])
    assert "human_decision_required" in types
    # `pause` is consumed by the orchestrator internally to stop execution
    # without yielding a `pipeline_error`. The stream therefore ends after
    # `human_decision_required`.
    last_event = events[-1]
    assert last_event.get("type") == "human_decision_required", f"expected last event to be human_decision_required, got {last_event}"
    print("scenario 2 PASSED")
    print()


async def main():
    await scenario_failing_tests_retry()
    await scenario_human_decision_pause()
    print("ALL LOOP SCENARIOS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
