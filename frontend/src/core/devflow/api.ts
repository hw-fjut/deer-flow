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

// ==================== Agent Chat Mode APIs ====================

export interface ChatSessionCreateRequest {
  agent_name: string;
  description?: string;
}

export interface ChatSessionSummary {
  session_id: string;
  project_id: string;
  agent_name: string;
  history_access: string;
  description: string;
  status: "active" | "closed";
  message_count: number;
  created_at: string;
  last_activity: string;
  metadata: Record<string, unknown>;
}

export interface ChatHistoryEntry {
  role: string;
  content: string;
  timestamp: string;
  metadata: Record<string, unknown>;
  human_decision: Record<string, unknown> | null;
  conversation_continuation: Record<string, unknown> | null;
}

export interface ChatSessionDetailResponse {
  session: ChatSessionSummary;
  messages: string[];
  history: ChatHistoryEntry[];
}

export interface ChatSendRequest {
  content: string;
  role?: string;
}

export interface ChatSendResponse {
  session: ChatSessionSummary;
  reply: {
    content: string;
    files: string[];
    success: boolean;
    error: string | null;
    metadata: Record<string, unknown>;
  };
  human_decision: Record<string, unknown> | null;
  conversation_continuation: Record<string, unknown> | null;
}

export interface AgentSummary {
  name: string;
  description: string;
  history_access: string;
  allowed_stages: string[];
  skill_count: number;
}

export async function listAgents(): Promise<AgentSummary[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/devflow/skills`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to list agents" }));
    throw new Error(error.detail || "Unknown error");
  }
  const data = await response.json();
  return Object.entries(data.agent_scopes || {}).map(([name, scope]: [string, any]) => ({
    name,
    description: scope.description || "",
    history_access: scope.history_access || "full",
    allowed_stages: scope.allowed_stages || [],
    skill_count: scope.skill_count || 0,
  }));
}

export async function createChatSession(
  projectId: string,
  request: ChatSessionCreateRequest
): Promise<ChatSessionSummary> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/chat/${projectId}/sessions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to create chat session" }));
    throw new Error(error.detail || "Unknown error");
  }
  const data = await response.json();
  return data.session as ChatSessionSummary;
}

export async function listChatSessions(
  projectId: string,
  onlyActive: boolean = true
): Promise<ChatSessionSummary[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/chat/${projectId}/sessions?only_active=${onlyActive}`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to list chat sessions" }));
    throw new Error(error.detail || "Unknown error");
  }
  const data = await response.json();
  return data.sessions as ChatSessionSummary[];
}

export async function getChatSession(sessionId: string): Promise<ChatSessionDetailResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/chat/sessions/${sessionId}`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get chat session" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function sendChatMessage(
  sessionId: string,
  request: ChatSendRequest
): Promise<ChatSendResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/chat/sessions/${sessionId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to send chat message" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function closeChatSession(sessionId: string): Promise<ChatSessionSummary> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/chat/sessions/${sessionId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to close chat session" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}

export async function reopenChatSession(sessionId: string): Promise<ChatSessionSummary> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/devflow/chat/sessions/${sessionId}/reopen`,
    { method: "POST" }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to reopen chat session" }));
    throw new Error(error.detail || "Unknown error");
  }
  return response.json();
}
