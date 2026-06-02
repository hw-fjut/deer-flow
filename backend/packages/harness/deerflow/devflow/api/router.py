"""API router for DevFlow.

Endpoints:

* ``POST /api/devflow/run`` - start a new pipeline
* ``POST /api/devflow/run/{id}/execute`` - execute (SSE)
* ``GET  /api/devflow/run/{id}/status`` - status
* ``GET  /api/devflow/projects`` - list projects
* ``POST /api/devflow/run/{id}/cancel`` - cancel pipeline
* ``POST /api/devflow/run/{id}/decisions`` - submit a human decision answer
* ``POST /api/devflow/run/{id}/conversations/{cid}/messages`` - continue a conversation
* ``GET  /api/devflow/run/{id}/decisions/pending`` - list pending decisions
* ``GET  /api/devflow/skills`` - list all configured skills
* ``GET  /api/devflow/skills/{agent}`` - list the skills of one agent
* ``POST /api/devflow/skills/reload`` - hot-reload all ``.md`` skill files

Workspace / File:
* ``GET  /api/devflow/workspaces`` - list workspaces
* ``POST /api/devflow/workspaces`` - create workspace
* ``DELETE /api/devflow/workspaces/{id}`` - delete workspace
* ``GET  /api/devflow/workspaces/{id}/files`` - list file tree
* ``GET  /api/devflow/workspaces/{id}/files/read`` - read file content

Chat sessions (mode):
* ``POST /api/devflow/chat/{project_id}/sessions`` - create chat session
* ``GET  /api/devflow/chat/{project_id}/sessions`` - list chat sessions
* ``GET  /api/devflow/chat/sessions/{session_id}`` - get session detail
* ``POST /api/devflow/chat/sessions/{session_id}/messages`` - send message
* ``DELETE /api/devflow/chat/sessions/{session_id}`` - close session
* ``POST /api/devflow/chat/sessions/{session_id}/reopen`` - reopen session
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from deerflow.devflow.common.skill_config import get_skill_loader
from deerflow.devflow.main_agent.orchestrator import DevFlowOrchestrator
from deerflow.devflow.memory.service import MemoryService

router = APIRouter(prefix="/api/devflow", tags=["devflow"])

orchestrator = DevFlowOrchestrator(memory_service=MemoryService())

# In-memory workspace / conversation storage (replace with a real DB in prod).
_workspaces: dict[str, dict[str, Any]] = {}
_conversations: dict[str, list[dict[str, Any]]] = {}
_chat_messages: dict[str, list[dict[str, Any]]] = {}


# =============================================================== run / pipeline
class PipelineCreate(BaseModel):
    name: str
    description: str
    max_loop_iterations: int | None = Field(default=None, ge=1, le=20)


class PipelineResponse(BaseModel):
    project_id: str
    name: str
    description: str
    status: str
    current_stage: str
    completed_stages: list[dict[str, Any]] = Field(default_factory=list)
    failed_stage: dict[str, Any] | None = None
    loop_iteration: int = 0
    max_loop_iterations: int = 5
    pending_decisions: list[dict[str, Any]] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    projects: list[PipelineResponse]


@router.post("/run", response_model=PipelineResponse)
async def start_devflow_run(request: PipelineCreate):
    if request.max_loop_iterations is not None:
        orchestrator.max_loop_iterations = request.max_loop_iterations
    state = await orchestrator.start_pipeline(name=request.name, description=request.description)
    return _serialize_state(state)


@router.post("/run/{project_id}/execute")
async def execute_devflow_run(project_id: str):
    state = await orchestrator.get_pipeline_status(project_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {project_id}")
    return StreamingResponse(
        _stream_events(orchestrator.execute_pipeline(project_id)),
        media_type="text/event-stream",
    )


@router.get("/run/{project_id}/status", response_model=PipelineResponse)
async def get_run_status(project_id: str):
    state = await orchestrator.get_pipeline_status(project_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {project_id}")
    return _serialize_state(state)


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects():
    projects = []
    for project_id in list(orchestrator.active_pipelines.keys()):
        state = await orchestrator.get_pipeline_status(project_id)
        if state:
            projects.append(_serialize_state(state))
    return ProjectListResponse(projects=projects)


@router.post("/run/{project_id}/cancel")
async def cancel_run(project_id: str, reason: str = "user_cancelled"):
    await orchestrator.cancel_pipeline(project_id, reason=reason)
    return {"project_id": project_id, "status": "cancelled"}


# --------------------------------------------------------------- decisions
class DecisionAnswer(BaseModel):
    decision_id: str
    answer: str


@router.get("/run/{project_id}/decisions/pending")
async def list_pending_decisions(project_id: str):
    return await orchestrator.get_pending_decisions(project_id)


@router.post("/run/{project_id}/decisions")
async def submit_decision(project_id: str, payload: DecisionAnswer):
    state = await orchestrator.get_pipeline_status(project_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {project_id}")
    return StreamingResponse(
        _stream_events(
            orchestrator.submit_human_decision(project_id, payload.decision_id, payload.answer)
        ),
        media_type="text/event-stream",
    )


# --------------------------------------------------------------- conversations
class ConversationMessage(BaseModel):
    role: str = "user"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/run/{project_id}/conversations/{conversation_id}/messages")
async def submit_conversation_message(
    project_id: str,
    conversation_id: str,
    payload: ConversationMessage,
):
    return await orchestrator.submit_conversation_message(
        project_id=project_id,
        conversation_id=conversation_id,
        content=payload.content,
        role=payload.role,
    )


class ChatSessionCreate(BaseModel):
    agent_name: str
    description: str = ""


class ChatMessagePayload(BaseModel):
    content: str
    role: str = "user"


# ============================================================== chat sessions
@router.post("/chat/{project_id}/sessions")
async def create_chat_session(project_id: str, payload: ChatSessionCreate):
    try:
        session = await orchestrator.start_chat_session(
            project_id=project_id,
            agent_name=payload.agent_name,
            description=payload.description,
        )
        return {"session": session.to_dict()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/chat/{project_id}/sessions")
async def list_chat_sessions(project_id: str, only_active: bool = True):
    return {"sessions": await orchestrator.list_chat_sessions(project_id=project_id, only_active=only_active)}


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str):
    result = await orchestrator.get_chat_session(session_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return result


@router.post("/chat/sessions/{session_id}/messages")
async def send_chat_message(session_id: str, payload: ChatMessagePayload):
    try:
        return await orchestrator.chat_with_agent(
            session_id=session_id,
            user_message=payload.content,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/chat/sessions/{session_id}")
async def close_chat_session(session_id: str):
    session = await orchestrator.close_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return session


@router.post("/chat/sessions/{session_id}/reopen")
async def reopen_chat_session(session_id: str):
    session = await orchestrator.reopen_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return session


# --------------------------------------------------------------- skills
@router.get("/skills")
async def list_all_skills():
    loader = get_skill_loader()
    return {
        "agents": loader.list_all_skills(),
        "agent_scopes": {
            agent: {
                "description": scope.description,
                "history_access": scope.history_access,
                "allowed_stages": scope.allowed_stages,
                "skill_count": len(scope.skills),
            }
            for agent, scope in ((a, loader.load_agent_scope(a)) for a in loader.list_agents())
        },
    }


@router.get("/skills/{agent_name}")
async def list_agent_skills(agent_name: str):
    loader = get_skill_loader()
    if agent_name not in loader.list_agents():
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}")
    scope = loader.load_agent_scope(agent_name)
    return {
        "agent": agent_name,
        "description": scope.description,
        "history_access": scope.history_access,
        "allowed_stages": scope.allowed_stages,
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "tools": s.tools,
                "constraints": s.constraints,
                "output_format": s.output_format,
                "file_path": str(s.file_path) if s.file_path else None,
            }
            for s in scope.skills
        ],
    }


@router.post("/skills/reload")
async def reload_skills():
    loader = get_skill_loader()
    loader.reload_all()
    return {"reloaded": True, "agents": loader.list_agents()}


# ============================================================== serialization
def _serialize_state(state) -> PipelineResponse:
    return PipelineResponse(
        project_id=state.project_id,
        name=state.name,
        description=state.description,
        status=state.status.value,
        current_stage=state.current_stage.value,
        completed_stages=[
            {
                "stage": r.stage.value,
                "success": r.success,
                "output": (r.output or "")[:200],
                "files": r.files,
                "error": r.error,
                "duration_seconds": r.duration_seconds,
            }
            for r in state.completed_stages
        ],
        failed_stage=(
            {"stage": state.failed_stage.stage.value, "error": state.failed_stage.error}
            if state.failed_stage
            else None
        ),
        loop_iteration=state.loop_iteration,
        max_loop_iterations=state.max_loop_iterations,
        pending_decisions=[
            {
                "id": d.id,
                "stage": d.stage,
                "question": d.question,
                "recommended_option": d.recommended_option,
                "status": d.status.value,
            }
            for d in state.pending_decisions
        ],
    )


async def _stream_events(events: AsyncGenerator[dict[str, Any], None]) -> AsyncGenerator[str, None]:
    async for event in events:
        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"


# ============================================================== workspace
class WorkspaceCreate(BaseModel):
    name: str
    path: str


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    path: str
    created_at: str


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces():
    return [
        WorkspaceResponse(id=ws_id, name=ws_data["name"], path=ws_data["path"], created_at=ws_data["created_at"])
        for ws_id, ws_data in _workspaces.items()
    ]


@router.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(request: WorkspaceCreate):
    ws_id = f"ws-{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    ws_path = Path(request.path)
    if not ws_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {request.path}")
    _workspaces[ws_id] = {"id": ws_id, "name": request.name, "path": request.path, "created_at": now}
    _conversations.setdefault(ws_id, [])
    return WorkspaceResponse(id=ws_id, name=request.name, path=request.path, created_at=now)


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    _workspaces.pop(workspace_id, None)
    _conversations.pop(workspace_id, None)
    return {"message": "Workspace deleted"}


# ============================================================== file tree
class FileTreeNode(BaseModel):
    name: str
    type: str  # "file" | "folder"
    path: str
    children: list["FileTreeNode"] | None = None


class FileTreeResponse(BaseModel):
    nodes: list[FileTreeNode]


class FileReadResponse(BaseModel):
    content: str
    path: str


def _build_file_tree(dir_path: Path, max_depth: int, current_depth: int = 0) -> list[FileTreeNode]:
    if current_depth > max_depth:
        return []
    if not dir_path.is_dir():
        return []
    nodes: list[FileTreeNode] = []
    try:
        for entry in sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            if entry.name in ("node_modules", "__pycache__", ".git", ".venv", "venv", ".next", "dist", "build"):
                continue
            if entry.is_dir():
                children = _build_file_tree(entry, max_depth, current_depth + 1) if max_depth > 0 else None
                nodes.append(
                    FileTreeNode(
                        name=entry.name,
                        type="folder",
                        path=str(entry.absolute()),
                        children=children if max_depth > 0 else None,
                    )
                )
            else:
                nodes.append(
                    FileTreeNode(
                        name=entry.name,
                        type="file",
                        path=str(entry.absolute()),
                        children=None,
                    )
                )
    except PermissionError:
        pass
    return nodes


@router.get("/workspaces/{workspace_id}/files", response_model=FileTreeResponse)
async def get_workspace_file_tree(workspace_id: str, max_depth: int = 3):
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws_path = Path(_workspaces[workspace_id]["path"])
    if not ws_path.exists():
        raise HTTPException(status_code=400, detail=f"Workspace path does not exist: {ws_path}")
    nodes = _build_file_tree(ws_path, max_depth)
    return FileTreeResponse(nodes=nodes)


@router.get("/workspaces/{workspace_id}/files/read", response_model=FileReadResponse)
async def read_workspace_file(workspace_id: str, file_path: str):
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws_path = Path(_workspaces[workspace_id]["path"]).resolve()
    target = Path(file_path).resolve()
    if not str(target).startswith(str(ws_path)):
        raise HTTPException(status_code=403, detail="File path is outside workspace")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    try:
        content = target.read_text(encoding="utf-8")
        return FileReadResponse(content=content, path=str(target))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")


# ============================================================== chat (compat)
class ChatMessage(BaseModel):
    content: str


@router.post("/workspaces/{workspace_id}/conversations/{conv_id}/messages")
async def send_message(workspace_id: str, conv_id: str, request: ChatMessage):
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    _chat_messages.setdefault(conv_id, []).append(
        {"role": "user", "content": request.content, "timestamp": datetime.now().isoformat()}
    )
    state = await orchestrator.start_pipeline(
        name=request.content[:30] or "DevFlow Project",
        description=request.content,
    )
    return StreamingResponse(
        _stream_chat_messages(conv_id, orchestrator.execute_pipeline(state.project_id)),
        media_type="text/event-stream",
    )


async def _stream_chat_messages(
    conv_id: str,
    events: AsyncGenerator[dict[str, Any], None],
) -> AsyncGenerator[str, None]:
    async for event in events:
        _chat_messages.setdefault(conv_id, []).append(
            {
                "role": "system",
                "content": json.dumps(event, ensure_ascii=False),
                "timestamp": event.get("timestamp", datetime.now().isoformat()),
                "event_type": event.get("type"),
            }
        )
        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"
