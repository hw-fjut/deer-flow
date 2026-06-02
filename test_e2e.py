"""End-to-end smoke test for the DevFlow pipeline."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"e:\sourceCode\deer-flow\backend\packages\harness")
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEVFLOW_MEMORY_DIR", tempfile.mkdtemp(prefix="devflow_e2e_"))

from deerflow.devflow.agents import get_agent_registry  # noqa: E402
from deerflow.devflow.common.conversation_state import (  # noqa: E402
    ConversationStateManager,
    ConversationTrigger,
)
from deerflow.devflow.common.human_decision import HumanDecisionManager  # noqa: E402
from deerflow.devflow.common.recovery import ErrorClassifier  # noqa: E402
from deerflow.devflow.common.skill_config import get_skill_loader  # noqa: E402
from deerflow.devflow.main_agent.orchestrator import DevFlowOrchestrator  # noqa: E402


async def run_e2e():
    print("== Discovering agents & skills ==")
    loader = get_skill_loader()
    agents = loader.list_agents()
    print("agents:", agents)
    for agent in agents:
        scope = loader.load_agent_scope(agent)
        print(f"  {agent}: history_access={scope.history_access}, skills={scope.skill_names()}")
    assert "frontend_design" in agents
    assert "spec_development" in agents
    assert "code_testing" in agents
    assert "deployment" in agents
    assert get_agent_registry()["frontend_design"].__name__ == "FrontendDesignAgent"

    print()
    print("== Running orchestrator end-to-end ==")
    orch = DevFlowOrchestrator(max_loop_iterations=3)
    state = await orch.start_pipeline(name="E2E Project", description="Build a tiny todo app")
    print("started pipeline:", state.project_id)

    events = []
    async for ev in orch.execute_pipeline(state.project_id):
        events.append(ev)
        if ev.get("type") in {
            "stage_start",
            "stage_complete",
            "loop_start",
            "loop_complete",
            "pipeline_complete",
            "pipeline_error",
            "human_decision_required",
        }:
            print(f"  event: {ev['type']:24s} stage={ev.get('stage', '-'):18s} iter={ev.get('iteration', '-')}")

    types = [e["type"] for e in events]
    assert "stage_start" in types
    assert "loop_start" in types
    assert "pipeline_complete" in types
    print("pipeline completed cleanly")

    status = await orch.get_pipeline_status(state.project_id)
    print()
    print("== Loop history ==")
    for r in status.loop_history:
        print(
            f"  iter={r.iteration} test_passed={r.test_passed} "
            f"deploy={r.deployment_validated} "
            f"exit={r.exit_reason.value if r.exit_reason else None}"
        )
    assert status.loop_iteration >= 1
    assert any(
        r.exit_reason and r.exit_reason.value in {"tests_passed", "deployment_validated"}
        for r in status.loop_history
    )

    print()
    print("== Human decision request ==")
    dec_mgr = HumanDecisionManager(default_timeout_hours=1)
    decision = dec_mgr.create_decision_request(
        stage="architecture",
        question="Which database should we use for the todo app?",
        background="The PRD requires a small relational store with JSON support.",
        options=[
            {"label": "PostgreSQL", "description": "Mature RDBMS, JSONB support, easy to host"},
            {"label": "SQLite", "description": "File-based, zero-config, no JSONB"},
        ],
        recommended_option="PostgreSQL",
        impact="PostgreSQL will be added to docker-compose; SQLite is single-node only.",
        related_artifacts=["ARCHITECTURE.md", "DEPLOYMENT.md"],
    )
    payload = dec_mgr.format_decision_payload(decision)
    assert payload["id"] == decision.id
    assert payload["recommended_option"] == "PostgreSQL"
    assert "PostgreSQL" in payload["message"]
    print("decision id:", decision.id, "deadline:", decision.deadline)
    print("--- formatted message ---")
    print(payload["message"])
    print("--- end formatted message ---")
    dec_mgr.resolve_decision(decision.id, "PostgreSQL")
    assert dec_mgr.get_decision(decision.id).status.value == "answered"

    print()
    print("== Conversation continuation ==")
    conv_mgr = ConversationStateManager(max_continuations=1)
    conv_id = conv_mgr.start_conversation(
        agent_name="spec_development",
        stage="spec_development",
        reason="initial clarification",
        trigger=ConversationTrigger.CLARIFICATION,
    )
    allowed, _ = conv_mgr.request_continuation(conv_id, "need more details on auth")
    assert allowed
    conv_mgr.append_message(conv_id, role="user", content="use OAuth2 with PKCE")
    allowed, _ = conv_mgr.request_continuation(conv_id, "what scopes?")
    assert not allowed  # max reached
    assert conv_mgr.should_escalate(conv_id)
    print("conversation correctly escalated after exhausting 1 continuation")

    print()
    print("== Error classification ==")
    classifier = ErrorClassifier()
    cls1 = classifier.classify(Exception("agent stage failed: timeout"))
    print("agent error ->", cls1.action.value, cls1.severity)
    cls2 = classifier.classify(Exception("context too long: 8000 tokens"))
    print("context error ->", cls2.action.value, cls2.severity)
    cls3 = classifier.classify(Exception("tool shell failed"))
    print("tool error ->", cls3.action.value, cls3.severity)

    # Test conversation continuation
    print()
    print("== Conversation continuation payload (orchestrator) ==")
    # Reuse the state we already created; simulate an in-pipeline conversation
    conv_id2 = conv_mgr.start_conversation(
        agent_name="frontend_design",
        stage="frontend_design",
        reason="ask about color scheme",
        trigger=ConversationTrigger.CONFIRM_APPROACH,
    )
    print("conversation id:", conv_id2, "max_continuations:", conv_mgr.max_continuations)

    print()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(run_e2e())
