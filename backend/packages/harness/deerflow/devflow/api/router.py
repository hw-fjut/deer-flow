"""API router definitions"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deerflow.devflow.api.schemas import (
    ChatMessage,
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    PipelineCreate,
    PipelineResponse,
    ProjectListResponse,
    WorkspaceCreate,
    WorkspaceResponse,
)
from deerflow.devflow.main_agent.orchestrator import DevFlowOrchestrator
from deerflow.devflow.memory.service import MemoryService

router = APIRouter(prefix="/api/devflow", tags=["devflow"])

# Global orchestrator instance
orchestrator = DevFlowOrchestrator(memory_service=MemoryService())

# Store workspaces (should be persisted to database in production)
_workspaces: dict[str, dict[str, Any]] = {}
_conversations: dict[str, list[dict[str, Any]]] = {}
_chat_messages: dict[str, list[dict[str, Any]]] = {}


@router.post("/run", response_model=PipelineResponse)
async def start_devflow_run(request: PipelineCreate):
    """Start full development workflow"""
    try:
        state = await orchestrator.start_pipeline(
            name=request.name,
            description=request.description,
        )
        
        return PipelineResponse(
            project_id=state.project_id,
            name=state.name,
            description=state.description,
            status=state.status.value,
            current_stage=state.current_stage.value,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/{project_id}/execute")
async def execute_devflow_run(project_id: str):
    """Execute pipeline with SSE streaming"""
    try:
        # Verify pipeline exists
        state = await orchestrator.get_pipeline_status(project_id)
        if not state:
            raise HTTPException(status_code=404, detail=f"Pipeline not found: {project_id}")
        
        return StreamingResponse(
            _stream_events(orchestrator.execute_pipeline(project_id)),
            media_type="text/event-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/run/{project_id}/status", response_model=PipelineResponse)
async def get_run_status(project_id: str):
    """Get pipeline status"""
    state = await orchestrator.get_pipeline_status(project_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {project_id}")
    
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
                "output": r.output[:200],
            }
            for r in state.completed_stages
        ],
        failed_stage={
            "stage": state.failed_stage.stage.value,
            "error": state.failed_stage.error,
        } if state.failed_stage else None,
    )


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects():
    """Get all projects list"""
    try:
        projects = await orchestrator.get_all_projects()
        return ProjectListResponse(
            projects=[PipelineResponse(**p) for p in projects]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _stream_events(events: AsyncGenerator[dict[str, Any], None]) -> AsyncGenerator[str, None]:
    """Convert async generator to SSE format"""
    async for event in events:
        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"


# ==================== Workspace APIs ====================

@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces():
    """Get all workspaces list"""
    workspaces = []
    for ws_id, ws_data in _workspaces.items():
        workspaces.append(WorkspaceResponse(
            id=ws_id,
            name=ws_data["name"],
            path=ws_data["path"],
            created_at=ws_data["created_at"],
        ))
    return workspaces


@router.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(request: WorkspaceCreate):
    """Create workspace"""
    ws_id = f"ws-{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    
    # Verify path exists
    ws_path = Path(request.path)
    if not ws_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {request.path}")
    
    workspace = {
        "id": ws_id,
        "name": request.name,
        "path": request.path,
        "created_at": now,
    }
    _workspaces[ws_id] = workspace
    _conversations[ws_id] = []
    
    return WorkspaceResponse(
        id=ws_id,
        name=request.name,
        path=request.path,
        created_at=now,
    )


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """Delete workspace"""
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    del _workspaces[workspace_id]
    if workspace_id in _conversations:
        del _conversations[workspace_id]
    if workspace_id in _chat_messages:
        del _chat_messages[workspace_id]
    
    return {"message": "Workspace deleted"}


# ==================== Conversation APIs ====================

@router.get("/workspaces/{workspace_id}/conversations")
async def list_conversations(workspace_id: str):
    """Get all conversations for workspace"""
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    conversations = _conversations.get(workspace_id, [])
    return [ConversationResponse(
        id=conv["id"],
        workspace_id=workspace_id,
        title=conv["title"],
        last_message=conv.get("last_message", ""),
        created_at=conv["created_at"],
    ) for conv in conversations]


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(request: ConversationCreate):
    """Create conversation"""
    if request.workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    
    conversation = {
        "id": conv_id,
        "title": request.title,
        "created_at": now,
        "last_message": "",
    }
    
    _conversations.setdefault(request.workspace_id, []).append(conversation)
    _chat_messages[conv_id] = []
    
    return ConversationResponse(
        id=conv_id,
        workspace_id=request.workspace_id,
        title=request.title,
        last_message="",
        created_at=now,
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete conversation"""
    for ws_id, convs in _conversations.items():
        _conversations[ws_id] = [c for c in convs if c["id"] != conversation_id]
    
    if conversation_id in _chat_messages:
        del _chat_messages[conversation_id]
    
    return {"message": "Conversation deleted"}


# ==================== Chat APIs ====================

@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    """Get conversation messages list"""
    messages = _chat_messages.get(conversation_id, [])
    return [ChatResponse(
        role=msg["role"],
        content=msg["content"],
        timestamp=msg["timestamp"],
    ) for msg in messages]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, request: ChatMessage):
    """Send message and trigger DevFlow pipeline (SSE streaming)"""
    if conversation_id not in _chat_messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    now = datetime.now().isoformat()
    
    # Add user message
    user_msg = {
        "role": "user",
        "content": request.content,
        "timestamp": now,
    }
    _chat_messages[conversation_id].append(user_msg)
    
    # Update conversation last message
    for ws_id, convs in _conversations.items():
        for conv in convs:
            if conv["id"] == conversation_id:
                conv["last_message"] = request.content[:50]
                break
    
    # Create DevFlow pipeline
    project_name = request.content[:30] or "DevFlow Project"
    state = await orchestrator.start_pipeline(
        name=project_name,
        description=request.content,
    )
    
    # Return SSE stream
    return StreamingResponse(
        _stream_chat_messages(conversation_id, orchestrator.execute_pipeline(state.project_id)),
        media_type="text/event-stream",
    )


@router.post("/conversations/{conversation_id}/messages/stream")
async def send_message_stream(conversation_id: str, request: ChatMessage):
    """Send message and trigger DevFlow pipeline (SSE streaming) - full implementation"""
    if conversation_id not in _chat_messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    now = datetime.now().isoformat()
    
    # Add user message
    user_msg = {
        "role": "user",
        "content": request.content,
        "timestamp": now,
    }
    _chat_messages[conversation_id].append(user_msg)
    
    # Update conversation last message
    for ws_id, convs in _conversations.items():
        for conv in convs:
            if conv["id"] == conversation_id:
                conv["last_message"] = request.content[:50]
                break
    
    # Create DevFlow pipeline
    project_name = request.content[:30] or "DevFlow Project"
    state = await orchestrator.start_pipeline(
        name=project_name,
        description=request.content,
    )
    
    # Return SSE stream
    return StreamingResponse(
        _stream_chat_messages(conversation_id, orchestrator.execute_pipeline(state.project_id)),
        media_type="text/event-stream",
    )


async def _stream_chat_messages(
    conversation_id: str,
    events: AsyncGenerator[dict[str, Any], None],
) -> AsyncGenerator[str, None]:
    """Convert pipeline events to chat message format and stream"""
    async for event in events:
        # Store each event in conversation history
        _chat_messages[conversation_id].append({
            "role": "system",
            "content": json.dumps(event, ensure_ascii=False),
            "timestamp": event.get("timestamp", datetime.now().isoformat()),
            "event_type": event.get("type"),
        })
        
        # Convert to SSE format
        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"


# ==================== File Tree API ====================

class FileTreeNode(BaseModel):
    """File tree node"""
    name: str
    type: str  # "file" or "folder"
    path: str
    children: list["FileTreeNode"] | None = None


class FileTreeResponse(BaseModel):
    """File tree response"""
    nodes: list[FileTreeNode]


@router.get("/workspaces/{workspace_id}/files", response_model=FileTreeResponse)
async def get_file_tree(workspace_id: str, max_depth: int = 5):
    """Get workspace file tree"""
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    ws_path = Path(_workspaces[workspace_id]["path"])
    if not ws_path.exists():
        raise HTTPException(status_code=400, detail="Workspace path does not exist")
    
    def build_tree(path: Path, current_depth: int = 0) -> list[FileTreeNode]:
        if current_depth >= max_depth:
            return []
        
        nodes = []
        try:
            for item in sorted(path.iterdir()):
                node = FileTreeNode(
                    name=item.name,
                    type="folder" if item.is_dir() else "file",
                    path=str(item),
                )
                if item.is_dir():
                    node.children = build_tree(item, current_depth + 1)
                nodes.append(node)
        except PermissionError:
            pass
        
        return nodes
    
    nodes = build_tree(ws_path)
    return FileTreeResponse(nodes=nodes)


@router.get("/workspaces/{workspace_id}/files/read")
async def read_file(workspace_id: str, file_path: str):
    """Read file content"""
    if workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    ws_path = Path(_workspaces[workspace_id]["path"])
    target_path = Path(file_path)
    
    # Security check: ensure file is within workspace
    try:
        target_path.resolve().relative_to(ws_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="File is not within workspace")
    
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    if target_path.is_dir():
        raise HTTPException(status_code=400, detail="Cannot read directory")
    
    try:
        content = target_path.read_text(encoding="utf-8")
        return {"content": content, "path": file_path}
    except UnicodeDecodeError:
        return {"content": "[Binary file]", "path": file_path}
