# DevFlow Pipeline Architecture

> A multi-agent software development pipeline. Linear head + iterative loop
> subgraph + standardized human-interaction layer.

## 1. High-Level Topology

```
                requirements (PRD + architecture)
                     |
                     v
             frontend_design
                     |
              loop subgraph
        +---------+---------+-----------+
        v         v         v           |
 spec_development code_testing deployment|
        \         |         /           |
         \        |        /            |
          v       v       v             |
         tests-passed?  deployment-valid?|
                    \    /               |
                     \  /                |
                  loop  exit (tests_passed / deployment_validated)
                       (max_iterations / human_decision / cancelled)
```

> The **linear head** is only two stages: `requirements` (which produces a
> combined PRD + architecture document) and `frontend_design`. The
> architecture step is folded into `requirements` because the two concerns
> are too tightly coupled to be worth splitting into separate stages.

The **linear head** (`requirements → frontend_design`) runs exactly once.
The **loop subgraph** (`spec_development → code_testing → deployment`)
repeats until either:

* the test report is green **and** the deployment validates
* the user cancels
* the configured `max_loop_iterations` is reached (default: 5)
* a sub-agent emits a Type-1 human decision request (pipeline paused)
* a sub-agent's Type-2 conversation budget is exhausted (escalated)

## 2. Stage Definitions

| Stage             | Type   | Reads                                       | Produces                                                                |
|-------------------|--------|---------------------------------------------|--------------------------------------------------------------------------|
| `requirements`    | linear | user task, conversation history            | `PRD.md` + `ARCHITECTURE.md` (combined body) - vision, personas, MoSCoW, acceptance criteria, stack, components, API design, deployment topology |
| `frontend_design` | linear | `requirements`                              | `design_tokens.md`, `page_blueprints.md`, `component_inventory.md`, `routing_and_state.md`, `api_contract_summary.md` |
| `spec_development`| loop   | `frontend_design` + previous-loop artifacts | `api_specs.md`, `data_models.md`, `interfaces.md`, `state_machines.md`    |
| `code_testing`    | loop   | `frontend_design` + `spec_development`     | `tests/*.py`, `coverage_report.html`                                    |
| `deployment`      | loop   | `frontend_design` + `code_testing`          | `Dockerfile`, `docker-compose.yml`, `k8s/deployment.yaml`, `DEPLOYMENT.md` |

## 3. Information Isolation

The orchestrator never sends the full conversation history to a loop-stage
agent. The per-stage context is built in
`DevFlowOrchestrator._build_stage_context()` and applies one of four
policies:

| Policy                               | Stages                          | Sees                                                              |
|--------------------------------------|---------------------------------|-------------------------------------------------------------------|
| `full`                               | requirements, frontend_design   | user task, prior stage artifacts, conversation history            |
| `frontend_design_only`               | spec_development                | frontend_design artifact + previous-iteration test report         |
| `frontend_design_and_spec`           | code_testing                    | frontend_design + spec_development artifacts                      |
| `frontend_design_and_testing`        | deployment                      | frontend_design + code_testing artifacts                          |

This is enforced at the orchestrator layer, **not** at the agent layer:
the agent has no way to widen its context.

## 4. Loop Subgraph Mechanics

The loop subgraph is implemented in `DevFlowOrchestrator._run_loop_subgraph`.
For every iteration the orchestrator:

1. Calls `state.start_loop_iteration()` (returns the new iteration number)
2. Runs `spec_development` → `code_testing` → `deployment` in order
3. After `code_testing` decides `test_passed` via `_is_test_report_green`
4. After `deployment` decides `deployment_validated` via `_is_deployment_valid`
5. If both green → exit with `LoopExitReason.TESTS_PASSED`
6. If `loop_iteration >= max_loop_iterations` → exit with `MAX_ITERATIONS`
7. Otherwise emit `loop_retry` event, reset `loop_stages_completed`, and run
   the three stages again

### 4.1 Termination Reasons

`LoopExitReason` values:

* `tests_passed` - normal completion (tests green + deployment validated)
* `deployment_validated` - reserved for pipelines that only validate deploy
* `max_iterations` - the configured ceiling was hit
* `human_decision` - a sub-agent paused the pipeline via a Type-1 request
* `pipeline_cancelled` - the user explicitly cancelled
* `escalated` - a Type-2 conversation ran out of continuations and a
  Type-1 request was created

### 4.2 Failure Recovery

`PipelineState.should_retry_loop()` exposes a synchronous predicate that the
UI can call to decide whether to keep iterating. The orchestrator itself
relies on `_is_test_report_green` / `_is_deployment_valid` heuristics that
look for markers in the agent output:

| Marker                          | Meaning                  |
|---------------------------------|--------------------------|
| `all tests passed` / `0 failed` | test report is green     |
| `coverage: NN%` (>= 80)         | coverage threshold met   |
| `failed` / `error` / `traceback`| test report is red       |
| `successfully deployed`         | deployment validated     |
| `deployment_invalid`            | deployment failed        |

Sub-classes can override these by replacing `_is_test_report_green` /
`_is_deployment_valid` on the orchestrator.

## 5. Human Interaction

Three kinds of human interaction are supported. They live in different
modules and use different state machines - a sub-agent can use Type-1 or
Type-2 mid-task; the user can also start a Type-3 chat session at any
time, completely outside the pipeline.

### 5.1 Type 1 - Human Decision Request

`HumanDecisionManager` (in `common/human_decision.py`) creates a
`HumanDecisionRequest` and yields a structured payload. The
orchestrator pauses the pipeline when a stage returns an
`AgentOutput.human_decision` payload.

The payload always contains:

| Field                 | Meaning                                                                 |
|-----------------------|-------------------------------------------------------------------------|
| `id`                  | `dec-XXXXXXXX` (short hash)                                             |
| `stage`               | The pipeline stage that emitted the request                             |
| `question`            | A single, well-formed question                                          |
| `background`          | Full context so the user can decide                                     |
| `options`             | 2-4 options, each with `label`, `description`, optional `impact`        |
| `recommended_option`  | The agent's recommendation (one of the labels)                          |
| `deadline`            | ISO timestamp (default: now + 24h)                                      |
| `impact`              | What changes if the user picks the recommended option                   |
| `related_artifacts`   | List of artifacts the decision will affect                              |
| `message`             | Pre-rendered markdown for the chat UI                                   |

Resolution:

* The user posts `{decision_id, answer}` to `POST /api/devflow/run/{id}/decisions`
* `HumanDecisionManager.resolve_decision()` validates against the option labels
* If the decision is *timed out* and the user does not respond, the
  manager applies the recommended option (`apply_timeout_fallback`)
* The orchestrator resumes the pipeline (callers POST the decision, the
  router replays `execute_pipeline`)

### 5.2 Type 2 - Conversation Continuation

`ConversationStateManager` (in `common/conversation_state.py`) keeps the
state of a *non-decision* conversation. It is invoked by an agent that
wants to keep talking with the user (clarification, confirm approach,
review a partial output) without forcing a hard decision.

State machine:

```
                    start_conversation()
                          |
                          v
                   in_progress -----------> completed
                          |   ^              ^
                          |   |              |
              request_continuation()  user posts message
                          |
                  (count < max_continuations)
                          |
                          v
                        blocked
                (exhausted -> escalated)
```

Each `request_continuation` increments the counter. When the counter
reaches `max_continuations` (default 3), `should_escalate()` returns
`True` and the orchestrator converts the conversation into a Type-1
decision request (`HumanDecisionManager.create_decision_request`) and
pauses the pipeline with exit reason `LoopExitReason.ESCALATED`.

### 5.3 Mid-Task Signaling

A sub-agent surfaces a Type-1 request by setting
`AgentOutput.human_decision`. A Type-2 request is surfaced via
`AgentOutput.conversation_continuation`. The base class provides
convenience helpers:

* `BaseSubAgent.request_human_decision(...)` - builds the payload
* `BaseSubAgent.request_conversation_continuation(...)` - increments
  the counter and returns the question

### 5.4 Type 3 - Direct Agent Chat (out of pipeline)

The third interaction mode is **chat**: the user picks a specific agent
and talks to it directly, no pipeline involved. The session is owned by
`ChatSessionManager` (`common/conversation_state.py`); the message
exchange goes through `DevFlowOrchestrator.chat_with_agent()`.

```
   user   -->  orchestrator.chat_with_agent(session_id, message)
                          |
                          v
                ChatSessionManager.append_message(role=user)
                          |
                          v
              build filtered context (per history_access)
                          |
                          v
              agent.execute(AgentInput{ mode=chat, chat_history })
                          |
                          v
           ChatSessionManager.append_message(role=agent, reply, ... )
```

* **No** pipeline state is touched - the pipeline can run independently
* Each session has its own project binding; chat sessions with different
  agents of the same project can co-exist
* `history_access` is resolved from the agent's `config.md` at session
  creation and **frozen** for the session's lifetime
* Sessions are *unlimited-turn* by default; no `max_continuations`
* An agent can still emit `human_decision` / `conversation_continuation`
  inside a chat reply - those signals are persisted on the message but
  do not pause any pipeline (because there is no pipeline)

The chat context builder (`DevFlowOrchestrator._build_chat_context`) is
the chat-mode counterpart of `_build_stage_context`. It enforces the
same per-agent visibility matrix described in Section 3.

## 6. Skill Configuration via `.md` Files

The whole system can be re-targeted by editing only Markdown files. The
loader (`common/skill_config.py`) discovers:

* `agents/<name>/config.md` - the agent's overall scope
* `agents/<name>/skills/<skill>.md` - individual skill blocks

Frontmatter schema (tiny YAML subset):

```yaml
---
name: skill_name
description: short description of the skill
tools: [file_write, file_read, ...]
constraints: [must_not_x, must_y, ...]
output_format: markdown
---
```

The agent's effective scope is rebuilt by `SkillConfigLoader.load_agent_scope()`.
Hot reload is supported via `POST /api/devflow/skills/reload`.

The frontend_design agent uses **five** skills, all defined as plain
`.md` files - editing them changes the agent's behaviour without any
Python change.

## 7. End-to-End Events

The orchestrator yields SSE-style events. The frontend subscribes to:

| Event type                  | Emitted by                | Meaning                              |
|-----------------------------|---------------------------|--------------------------------------|
| `stage_start`               | orchestrator              | Stage is about to run                |
| `stage_complete`            | orchestrator              | Stage finished successfully          |
| `stage_failed`              | orchestrator              | Stage failed                         |
| `loop_start`                | loop subgraph             | New loop iteration starts            |
| `loop_retry`                | loop subgraph             | Loop will retry                      |
| `loop_complete`             | loop subgraph             | Loop exited with success             |
| `loop_retry_exhausted`      | loop subgraph             | Loop exited with `max_iterations`    |
| `human_decision_required`   | orchestrator              | Pipeline paused for user decision    |
| `conversation_continuation` | orchestrator              | Mid-task conversation event          |
| `pipeline_complete`         | orchestrator              | Pipeline completed                   |
| `pipeline_error`            | orchestrator              | Pipeline failed unrecoverably        |

`pause` events are internal - the orchestrator consumes them to stop
the stream without surfacing an error.

## 8. API Surface

| Method | Path                                                | Purpose                  |
|--------|-----------------------------------------------------|--------------------------|
| POST   | `/api/devflow/run`                                  | Start a new pipeline     |
| POST   | `/api/devflow/run/{id}/execute`                     | Run (SSE)                |
| GET    | `/api/devflow/run/{id}/status`                      | Status                   |
| GET    | `/api/devflow/projects`                             | List projects            |
| POST   | `/api/devflow/run/{id}/cancel`                      | Cancel                   |
| GET    | `/api/devflow/run/{id}/decisions/pending`           | Pending decisions        |
| POST   | `/api/devflow/run/{id}/decisions`                   | Submit decision answer   |
| POST   | `/api/devflow/run/{id}/conversations/{cid}/messages`| Continue conversation    |
| GET    | `/api/devflow/skills`                               | List all skills          |
| GET    | `/api/devflow/skills/{agent}`                       | List agent skills        |
| POST   | `/api/devflow/skills/reload`                        | Hot-reload `.md` files   |
| POST   | `/api/devflow/chat/{project_id}/sessions`           | Start a chat session with one agent |
| GET    | `/api/devflow/chat/{project_id}/sessions`           | List chat sessions (filter by `only_active`) |
| GET    | `/api/devflow/chat/sessions/{session_id}`           | Get chat session + history |
| POST   | `/api/devflow/chat/sessions/{session_id}/messages`  | Send a message to the bound agent |
| DELETE | `/api/devflow/chat/sessions/{session_id}`           | Close a chat session     |
| POST   | `/api/devflow/chat/sessions/{session_id}/reopen`    | Reopen a closed session  |

The chat routes are **independent** of the pipeline routes: a chat
session does not require a pipeline to be running, and a running
pipeline is not affected by chat activity.

## 9. Error Recovery

`common/recovery.py` provides:

* `ErrorClassifier` - categorises exceptions by `ErrorKind` (agent /
  tool / memory / context-too-large / human-decision-timeout / cancelled)
  and returns a `RecoveryAction` (`retry_stage`, `retry_tool`,
  `use_partial_output`, `escalate_to_human`, `timeout_fallback`,
  `exit_loop`, `fail_pipeline`, `skip_and_continue`)
* `async_retry` - generic async retry decorator
* `PartialOutput` - structured "I have partial output" declaration
* `trace_context` - lightweight trace id context manager

Sub-classes can wrap their `execute()` with `@async_retry(...)` and call
`ErrorClassifier` on caught exceptions to decide whether to escalate to
the human or just retry the stage.
