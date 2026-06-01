/** DevFlow API 接口 */

import { getBackendBaseURL } from "@/core/config";
import { fetch } from "@/core/api/fetcher";

export interface WorkspaceCreateRequest {
  name: string;
  path: string;
}

export interface WorkspaceResponse {
  id: string;
  name: string;
  path: string;
  created_at: string;
}

export interface ConversationCreateRequest {
  workspace_id: string;
  title: string;
}

export interface ConversationResponse {
  id: string;
  workspace_id: string;
  title: string;
  last_message: string;
  created_at: string;
}

export interface ChatMessageRequest {
  workspace_id: string;
  conversation_id: string;
  content: string;
}

export interface ChatMessageResponse {
  role: string;
  content: string;
  timestamp: string;
}

export interface FileTreeNode {
  name: string;
  type: "file" | "folder";
  path: string;
  children?: FileTreeNode[];
}

export interface FileTreeResponse {
  nodes: FileTreeNode[];
}

export interface PipelineCreateRequest {
  name: string;
  description: string;
}

export interface PipelineResponse {
  project_id: string;
  name: string;
  description: string;
  status: string;
  current_stage: string;
  completed_stages: Array<{
    stage: string;
    success: boolean;
    output: string;
  }>;
  failed_stage?: {
    stage: string;
    error: string;
  };
}

// ==================== Workspace APIs ====================

export async function listWorkspaces(): Promise<WorkspaceResponse[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/devflow/workspaces`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to list workspaces" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function createWorkspace(request: WorkspaceCreateRequest): Promise<WorkspaceResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/devflow/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to create workspace" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  const response = await fetch(`${getBackendBaseURL()}/api/devflow/workspaces/${workspaceId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to delete workspace" }));
    throw new Error(error.detail || "Unknown error");
  }
}

// ==================== Conversation APIs ====================

export async function listConversations(workspaceId: string): Promise<ConversationResponse[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/workspaces/${workspaceId}/conversations`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to list conversations" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function createConversation(
  request: ConversationCreateRequest
): Promise<ConversationResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/devflow/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to create conversation" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/conversations/${conversationId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to delete conversation" }));
    throw new Error(error.detail || "Unknown error");
  }
}

// ==================== Chat APIs ====================

export async function getMessages(conversationId: string): Promise<ChatMessageResponse[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/conversations/${conversationId}/messages`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get messages" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function sendMessage(
  conversationId: string,
  request: ChatMessageRequest
): Promise<ChatMessageResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to send message" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

// ==================== File Tree APIs ====================

export async function getFileTree(workspaceId: string, maxDepth = 5): Promise<FileTreeResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/workspaces/${workspaceId}/files?max_depth=${maxDepth}`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get file tree" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function readFile(workspaceId: string, filePath: string): Promise<{ content: string; path: string }> {
  const encodedPath = encodeURIComponent(filePath);
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/workspaces/${workspaceId}/files/read?file_path=${encodedPath}`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to read file" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

// ==================== Pipeline APIs ====================

export async function startPipeline(request: PipelineCreateRequest): Promise<PipelineResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/devflow/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to start pipeline" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function getPipelineStatus(projectId: string): Promise<PipelineResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/run/${projectId}/status`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get pipeline status" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}
