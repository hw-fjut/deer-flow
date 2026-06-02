"""End-to-end test for the chat mode (single-agent direct conversation)."""
import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(r"e:\sourceCode\deer-flow\backend\packages\harness")
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEVFLOW_MEMORY_DIR", tempfile.mkdtemp(prefix="devflow_chat_"))

from deerflow.devflow.main_agent.orchestrator import DevFlowOrchestrator  # noqa: E402


async def main():
    print("== Chat mode - direct conversation with a single agent ==")
    orch = DevFlowOrchestrator()
    project_id = "chatproj-" + uuid.uuid4().hex[:6]
    print("project_id:", project_id)

    # 1) Start a session with each of the 5 agents. The orchestrator may
    #    create a brand-new project if the supplied project_id is unknown
    #    and then bind the session to the actual project_id it generated;
    #    we therefore capture the *first* canonical project_id and reuse
    #    it for every subsequent start_chat_session call.
    sessions = {}
    real_project_id: str | None = None
    for agent in ["requirements", "frontend_design", "spec_development", "code_testing", "deployment"]:
        s = await orch.start_chat_session(
            project_id=(real_project_id or project_id),
            agent_name=agent,
            description="Chat with " + agent,
        )
        if real_project_id is None:
            real_project_id = s.project_id
        sessions[agent] = s.session_id
        print("  started:", agent, "->", s.session_id, "(policy=" + s.history_access + ")")
    assert real_project_id is not None
    print("  real_project_id:", real_project_id)

    # 2) Send 2 messages to the spec_development chat
    print()
    print("== spec_development chat (2 turns) ==")
    spec_sid = sessions["spec_development"]
    r1 = await orch.chat_with_agent(spec_sid, "Define the auth API: list 3 endpoints with verbs and paths")
    print("  reply[1]:", r1["reply"]["content"].splitlines()[0] if r1["reply"]["content"] else "(empty)")
    r2 = await orch.chat_with_agent(spec_sid, "Now give me the error model for those 3 endpoints")
    print("  reply[2]:", r2["reply"]["content"].splitlines()[0] if r2["reply"]["content"] else "(empty)")

    info = await orch.get_chat_session(spec_sid)
    assert info is not None
    assert len(info["history"]) == 4, "expected 4 history messages, got " + str(len(info["history"]))
    print("  history length:", len(info["history"]), "(2 user + 2 agent) OK")

    # 3) Send a message to code_testing - it should NOT see spec_development's
    #    *chat history* (it may still see the spec_development artifact, which
    #    is permitted by its frontend_design_and_spec policy).
    print()
    print("== code_testing chat - history isolation ==")
    ct_sid = sessions["code_testing"]
    r3 = await orch.chat_with_agent(ct_sid, "Show me the latest test report status")
    assert r3["reply"]["success"]
    print("  reply content includes 'code_testing' or 'chat reply':", "code_testing" in r3["reply"]["content"] or "chat reply" in r3["reply"]["content"])
    info2 = await orch.get_chat_session(ct_sid)
    # The previous spec_development chat turn was "Define the auth API: list 3
    # endpoints with verbs and paths". That exact wording must NOT appear in
    # the code_testing session's history.
    forbidden = "Define the auth API: list 3 endpoints"
    assert forbidden not in str(info2["history"]), "code_testing chat must not see spec_development chat history"
    print("  history isolation verified OK (no cross-session messages leaked)")

    # 4) List and close sessions
    print()
    print("== Session lifecycle ==")
    listed = await orch.list_chat_sessions(project_id=real_project_id, only_active=True)
    print("  active sessions:", len(listed))
    assert len(listed) == 5
    closed = await orch.close_chat_session(spec_sid)
    assert closed and closed["status"] == "closed"
    listed2 = await orch.list_chat_sessions(project_id=real_project_id, only_active=True)
    print("  active after close:", len(listed2), "(expected 4)")
    assert len(listed2) == 4

    # 5) Try sending a message to a closed session
    print()
    print("== Sending to closed session should fail ==")
    try:
        await orch.chat_with_agent(spec_sid, "hi?")
        assert False, "should have raised"
    except Exception as e:
        print("  raised as expected:", e)
        assert "not active" in str(e)

    # 6) Reopen and send
    reopened = await orch.reopen_chat_session(spec_sid)
    assert reopened and reopened["status"] == "active"
    r4 = await orch.chat_with_agent(spec_sid, "ok thanks")
    assert r4["reply"]["success"]
    print("  reopen + send OK")

    # 7) Verify list of all sessions (active + closed)
    all_listed = await orch.list_chat_sessions(project_id=real_project_id, only_active=False)
    assert len(all_listed) == 5
    print("  all sessions:", len(all_listed), "(active + closed)")

    # 8) Verify the agent's history_access_policy is enforced
    print()
    print("== History access policy per agent ==")
    expected = {
        "requirements": "full",
        "frontend_design": "full",
        "spec_development": "frontend_design_only",
        "code_testing": "frontend_design_and_spec",
        "deployment": "frontend_design_and_testing",
    }
    for agent, exp_policy in expected.items():
        s = await orch.get_chat_session(sessions[agent])
        actual = s["session"]["history_access"]
        status = "OK" if actual == exp_policy else "FAIL"
        print("  ", status, agent, "expected=" + exp_policy, "actual=" + actual)
        assert actual == exp_policy, agent + ": expected " + exp_policy + ", got " + actual

    print()
    print("ALL CHAT MODE CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
