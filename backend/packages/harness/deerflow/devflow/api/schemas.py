"""API request/response models"""
from pydantic import BaseModel, Field
from typing import Any


class PipelineCreate(BaseModel):
    """Create pipeline request"""
    name: str = Field(description="Project name")
    description: str = Field(description="Project description")


class PipelineResponse(BaseModel):
    """Pipeline response"""
    project_id: str
    name: str
    description: str
    status: str
    current_stage: str
    completed_stages: list[dict[str, Any]] = []
    failed_stage: dict[str, Any] | None = None


class PipelineStatusResponse(BaseModel):
    """Pipeline status response"""
    project_id: str
    status: str
    current_stage: str
    progress: dict[str, Any]


class ProjectListResponse(BaseModel):
    """Project list response"""
    projects: list[PipelineResponse]


class WorkspaceCreate(BaseModel):
    """Create workspace request"""
    name: str = Field(description="Workspace name")
    path: str = Field(description="Workspace path")


class WorkspaceResponse(BaseModel):
    """Workspace response"""
    id: str
    name: str
    path: str
    created_at: str


class ConversationCreate(BaseModel):
    """Create conversation request"""
    workspace_id: str = Field(description="Workspace ID")
    title: str = Field(description="Conversation title")


class ConversationResponse(BaseModel):
    """Conversation response"""
    id: str
    workspace_id: str
    title: str
    last_message: str
    created_at: str


class ChatMessage(BaseModel):
    """Chat message"""
    workspace_id: str = Field(description="Workspace ID")
    conversation_id: str = Field(description="Conversation ID")
    content: str = Field(description="Message content")


class ChatResponse(BaseModel):
    """Chat response"""
    role: str
    content: str
    timestamp: str
