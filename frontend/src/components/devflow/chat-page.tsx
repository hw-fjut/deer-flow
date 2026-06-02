"use client";

import { BotIcon, MessageSquarePlusIcon, PlusIcon, SendIcon, StopCircleIcon, WorkflowIcon, XIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { getBackendBaseURL } from "@/core/config";

import type {
  AgentSummary,
  ChatHistoryEntry,
  ChatMessageResponse,
  ChatSessionDetailResponse,
  ChatSessionSummary,
  ConversationResponse,
  FileTreeNode,
} from "@/core/devflow/api";
import {
  closeChatSession,
  createChatSession,
  createConversation,
  deleteConversation,
  getChatSession,
  getMessages,
  listAgents,
  listChatSessions,
  listConversations,
  readFile,
  reopenChatSession,
  sendChatMessage,
} from "@/core/devflow/api";

import { FileTree } from "./file-tree";

type WorkspaceMode = "pipeline" | "chat";

interface DevFlowChatPageProps {
  workspaceId: string;
  workspaceName: string;
  workspacePath: string;
  onBack: () => void;
}

export function DevFlowChatPage({
  workspaceId,
  workspaceName,
  workspacePath,
  onBack,
}: DevFlowChatPageProps) {
  const { t } = useI18n();
  const [mode, setMode] = useState<WorkspaceMode>("pipeline");

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            ←
          </Button>
          <div>
            <h1 className="text-sm font-semibold">{workspaceName}</h1>
            <p className="truncate text-xs text-muted-foreground">{workspacePath}</p>
          </div>
        </div>
        <div className="flex items-center gap-1 rounded-md border p-1">
          <Button
            size="sm"
            variant={mode === "pipeline" ? "default" : "ghost"}
            onClick={() => setMode("pipeline")}
            className="h-7 gap-1"
          >
            <WorkflowIcon className="h-3.5 w-3.5" />
            {t.devflow.modePipeline}
          </Button>
          <Button
            size="sm"
            variant={mode === "chat" ? "default" : "ghost"}
            onClick={() => setMode("chat")}
            className="h-7 gap-1"
          >
            <BotIcon className="h-3.5 w-3.5" />
            {t.devflow.modeChat}
          </Button>
        </div>
      </header>
      <div className="flex-1 overflow-hidden">
        {mode === "pipeline" ? (
          <PipelineMode workspaceId={workspaceId} workspaceName={workspaceName} workspacePath={workspacePath} />
        ) : (
          <ChatMode
            workspaceId={workspaceId}
            workspaceName={workspaceName}
            workspacePath={workspacePath}
          />
        )}
      </div>
    </div>
  );
}

// ================================================================ Pipeline Mode

function PipelineMode({
  workspaceId,
  workspaceName,
  workspacePath,
}: {
  workspaceId: string;
  workspaceName: string;
  workspacePath: string;
}) {
  const { t } = useI18n();
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessageResponse[]>([]);
  const [isCreatingConv, setIsCreatingConv] = useState(false);
  const [newConvTitle, setNewConvTitle] = useState("");
  const [fileView, setFileView] = useState<{ name: string; content: string } | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await listConversations(workspaceId);
        setConversations(data);
        if (data.length > 0) {
          setActiveConversation(data[0]!.id);
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to load conversations");
      }
    }
    load();
  }, [workspaceId]);

  useEffect(() => {
    if (!activeConversation) return;
    const convId: string = activeConversation;
    async function load() {
      try {
        const data = await getMessages(convId);
        setMessages(data);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to load messages");
      }
    }
    load();
  }, [activeConversation]);

  const handleCreateConversation = useCallback(async () => {
    if (!newConvTitle.trim()) return;
    try {
      const conv = await createConversation({
        workspace_id: workspaceId,
        title: newConvTitle.trim(),
      });
      setConversations((prev) => [...prev, conv]);
      setActiveConversation(conv.id);
      setMessages([]);
      setIsCreatingConv(false);
      setNewConvTitle("");
      toast.success("会话已创建");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建失败");
    }
  }, [workspaceId, newConvTitle]);

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      try {
        await deleteConversation(id);
        setConversations((prev) => prev.filter((c) => c.id !== id));
        if (activeConversation === id) {
          setActiveConversation(null);
          setMessages([]);
        }
        toast.success("会话已删除");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "删除失败");
      }
    },
    [activeConversation]
  );

  const handleSendMessage = useCallback(async () => {
    if (!inputValue.trim() || !activeConversation || isLoading) return;

    const userMsg: ChatMessageResponse = {
      role: "user",
      content: inputValue,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputValue("");
    setIsLoading(true);

    try {
      const response = await fetch(
        `${getBackendBaseURL()}/api/devflow/conversations/${activeConversation}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workspace_id: workspaceId,
            conversation_id: activeConversation,
            content: inputValue,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Failed to send message" }));
        throw new Error(error.detail || "Unknown error");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("Failed to read response stream");

      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              let chatMsg: ChatMessageResponse | null = null;
              switch (event.type) {
                case "stage_start":
                  chatMsg = { role: "assistant", content: `开始阶段: ${event.stage}`, timestamp: event.timestamp };
                  break;
                case "stage_complete":
                  chatMsg = {
                    role: "assistant",
                    content: `✅ 阶段完成: ${event.stage}\n\n${event.output || ""}`,
                    timestamp: event.timestamp,
                  };
                  break;
                case "stage_failed":
                  chatMsg = {
                    role: "assistant",
                    content: `❌ 阶段失败: ${event.stage}\n\n错误: ${event.error || "未知错误"}`,
                    timestamp: event.timestamp,
                  };
                  break;
                case "pipeline_complete":
                  chatMsg = {
                    role: "assistant",
                    content: `🎉 DevFlow 流水线完成!\n\n项目ID: ${event.project_id}`,
                    timestamp: event.timestamp,
                  };
                  break;
                case "pipeline_error":
                  chatMsg = {
                    role: "assistant",
                    content: `流水线执行失败\n\n错误: ${event.error || "未知错误"}`,
                    timestamp: event.timestamp,
                  };
                  break;
              }
              if (chatMsg) setMessages((prev) => [...prev, chatMsg!]);
            } catch {
              // ignore
            }
          }
        }
      }

      setConversations((prev) =>
        prev.map((c) => (c.id === activeConversation ? { ...c, last_message: inputValue.slice(0, 50) } : c))
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "发送失败";
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, activeConversation, isLoading, workspaceId]);

  const handleFileClick = useCallback(
    async (node: FileTreeNode) => {
      try {
        const data = await readFile(workspaceId, node.path);
        setFileView({ name: node.name, content: data.content });
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "读取文件失败");
      }
    },
    [workspaceId]
  );

  const activeConv = conversations.find((c) => c.id === activeConversation);

  return (
    <div className="flex h-full">
      <div className="flex w-72 flex-col border-r">
        <div className="border-b px-4 py-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-1"
            onClick={() => setIsCreatingConv(!isCreatingConv)}
          >
            <MessageSquarePlusIcon className="h-4 w-4" />
            {t.devflow.newConversation}
          </Button>
        </div>
        {isCreatingConv && (
          <div className="border-b px-4 py-3">
            <Textarea
              placeholder="会话标题"
              value={newConvTitle}
              onChange={(e) => setNewConvTitle(e.target.value)}
              rows={2}
              className="resize-none"
            />
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={handleCreateConversation} className="flex-1">
                {t.devflow.create}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setIsCreatingConv(false);
                  setNewConvTitle("");
                }}
              >
                {t.devflow.cancel}
              </Button>
            </div>
          </div>
        )}
        <div className="flex-1 overflow-y-auto">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`group cursor-pointer px-4 py-2.5 transition-colors hover:bg-accent ${
                conv.id === activeConversation ? "bg-accent" : ""
              }`}
              onClick={() => setActiveConversation(conv.id)}
            >
              <div className="flex items-center justify-between">
                <p className="truncate text-sm font-medium">{conv.title}</p>
                <button
                  className="rounded p-1 opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteConversation(conv.id);
                  }}
                >
                  ×
                </button>
              </div>
              {conv.last_message && (
                <p className="truncate text-xs text-muted-foreground">{conv.last_message}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b px-4 py-2">
          <h3 className="font-medium">{activeConv?.title || "选择一个会话"}</h3>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-sm text-muted-foreground">
                <p>开始你的对话吧</p>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`rounded-lg px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-primary/10 ml-8"
                      : msg.role === "system"
                        ? "bg-muted/50"
                        : "mr-8"
                  }`}
                >
                  <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                </div>
              ))
            )}
          </div>
        </div>
        <div className="border-t px-4 py-3">
          <div className="mx-auto max-w-3xl">
            <div className="flex gap-2">
              <Textarea
                placeholder={t.devflow.sendMessagePlaceholder}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                disabled={isLoading || !activeConversation}
                className="min-h-[48px] resize-none"
              />
              {isLoading ? (
                <Button variant="destructive" size="icon" onClick={() => setIsLoading(false)}>
                  <StopCircleIcon className="h-4 w-4" />
                </Button>
              ) : (
                <Button
                  size="icon"
                  onClick={handleSendMessage}
                  disabled={!inputValue.trim() || !activeConversation}
                >
                  <SendIcon className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex w-64 flex-col border-l">
        {fileView ? (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b px-3 py-2">
              <span className="truncate text-sm font-medium">{fileView.name}</span>
              <button
                className="rounded px-2 py-1 text-xs hover:bg-accent"
                onClick={() => setFileView(null)}
              >
                关闭
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-3 text-xs">{fileView.content}</pre>
          </div>
        ) : (
          <FileTree
            workspaceName={workspaceName}
            workspacePath={workspacePath}
            workspaceId={workspaceId}
            onFileClick={handleFileClick}
          />
        )}
      </div>
    </div>
  );
}

// ================================================================= Chat Mode

function ChatMode({
  workspaceId,
  workspaceName,
  workspacePath,
}: {
  workspaceId: string;
  workspaceName: string;
  workspacePath: string;
}) {
  const { t } = useI18n();
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<ChatSessionDetailResponse | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const [fileView, setFileView] = useState<{ name: string; content: string } | null>(null);
  const [projectId] = useState<string>(() => `chat-${workspaceId}`);

  useEffect(() => {
    async function load() {
      try {
        const [ag, sess] = await Promise.all([listAgents(), listChatSessions(projectId, true)]);
        setAgents(ag);
        setSessions(sess);
        if (sess.length > 0) {
          setActiveSessionId(sess[0]!.session_id);
        }
      } catch (err) {
        // Silently handle - may be first load with no sessions yet
      }
    }
    load();
  }, [projectId]);

  useEffect(() => {
    if (!activeSessionId) {
      setActiveSession(null);
      return;
    }
    async function load() {
      try {
        const detail = await getChatSession(activeSessionId!);
        setActiveSession(detail);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to load session");
      }
    }
    load();
  }, [activeSessionId]);

  const refreshSessions = useCallback(async () => {
    try {
      const data = await listChatSessions(projectId, true);
      setSessions(data);
    } catch {
      // ignore
    }
  }, [projectId]);

  const handleStartChat = useCallback(
    async (agentName: string) => {
      try {
        const session = await createChatSession(projectId, {
          agent_name: agentName,
          description: `${t.devflow.chatWithAgent}: ${agentName}`,
        });
        await refreshSessions();
        setActiveSessionId(session.session_id);
        setShowAgentPicker(false);
        toast.success(`已与 ${agentName} 开始对话`);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "创建会话失败");
      }
    },
    [projectId, refreshSessions, t.devflow.chatWithAgent]
  );

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || !activeSessionId || isLoading) return;
    setIsLoading(true);
    const userContent = inputValue;
    setInputValue("");
    try {
      const resp = await sendChatMessage(activeSessionId, { content: userContent });
      setActiveSession((prev) => {
        if (!prev) return prev;
        const history = prev.history ? [...prev.history] : [];
        history.push({
          role: "user",
          content: userContent,
          timestamp: new Date().toISOString(),
          metadata: {},
          human_decision: null,
          conversation_continuation: null,
        });
        history.push({
          role: "agent",
          content: resp.reply.content,
          timestamp: new Date().toISOString(),
          metadata: resp.reply.metadata || {},
          human_decision: resp.human_decision,
          conversation_continuation: resp.conversation_continuation,
        });
        return {
          ...prev,
          session: resp.session,
          history,
          messages: [],
        };
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "发送失败");
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, activeSessionId, isLoading]);

  const handleClose = useCallback(
    async (sessionId: string) => {
      try {
        await closeChatSession(sessionId);
        await refreshSessions();
        if (activeSessionId === sessionId) {
          setActiveSessionId(null);
          setActiveSession(null);
        }
        toast.success("会话已关闭");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "关闭失败");
      }
    },
    [activeSessionId, refreshSessions]
  );

  const handleReopen = useCallback(
    async (sessionId: string) => {
      try {
        await reopenChatSession(sessionId);
        await refreshSessions();
        setActiveSessionId(sessionId);
        toast.success("会话已重新打开");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "重开失败");
      }
    },
    [refreshSessions]
  );

  const handleFileClick = useCallback(
    async (node: FileTreeNode) => {
      try {
        const data = await readFile(workspaceId, node.path);
        setFileView({ name: node.name, content: data.content });
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "读取文件失败");
      }
    },
    [workspaceId]
  );

  const activeAgent = activeSession
    ? agents.find((a) => a.name === activeSession.session.agent_name)
    : undefined;

  return (
    <div className="flex h-full">
      <div className="flex w-72 flex-col border-r">
        <div className="border-b px-4 py-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-1"
            onClick={() => setShowAgentPicker(true)}
          >
            <PlusIcon className="h-4 w-4" />
            {t.devflow.newAgentChat}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessions.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center text-xs text-muted-foreground">
              <BotIcon className="mb-2 h-6 w-6 opacity-50" />
              <p>{t.devflow.noChatSessions}</p>
            </div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.session_id}
                className={`group cursor-pointer px-4 py-2.5 transition-colors hover:bg-accent ${
                  s.session_id === activeSessionId ? "bg-accent" : ""
                }`}
                onClick={() => setActiveSessionId(s.session_id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium">{s.agent_name}</p>
                  {s.status === "closed" ? (
                    <Badge variant="secondary" className="text-[10px]">
                      {t.devflow.sessionClosed}
                    </Badge>
                  ) : null}
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {s.description || t.devflow.messageCount(s.message_count)}
                </p>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        {!activeSession ? (
          <div className="flex flex-1 flex-col items-center justify-center text-sm text-muted-foreground">
            <BotIcon className="mb-3 h-10 w-10 opacity-50" />
            <p>{t.devflow.selectAgentPrompt}</p>
            <Button className="mt-4" onClick={() => setShowAgentPicker(true)}>
              {t.devflow.selectAgent}
            </Button>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3 border-b px-4 py-2">
              <div className="min-w-0">
                <h3 className="flex items-center gap-2 truncate text-sm font-semibold">
                  <BotIcon className="h-4 w-4 text-primary" />
                  {activeSession.session.agent_name}
                </h3>
                {activeAgent ? (
                  <p className="truncate text-xs text-muted-foreground">
                    {t.devflow.historyAccessPolicy}: {activeAgent.history_access} · {activeAgent.skill_count} skills
                  </p>
                ) : null}
              </div>
              <div className="flex gap-2">
                {activeSession.session.status === "active" ? (
                  <Button size="sm" variant="outline" onClick={() => handleClose(activeSession.session.session_id)}>
                    <XIcon className="h-3.5 w-3.5" />
                    {t.devflow.close}
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => handleReopen(activeSession.session.session_id)}>
                    {t.devflow.reopen}
                  </Button>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              <div className="mx-auto max-w-3xl space-y-3">
                {(!activeSession.history || activeSession.history.length === 0) ? (
                  <div className="flex h-full flex-col items-center justify-center text-sm text-muted-foreground">
                    {t.devflow.noMessages}
                  </div>
                ) : (
                  activeSession.history.map((msg: ChatHistoryEntry, idx: number) => {
                    const isUser = msg.role === "user";
                    return (
                      <div key={idx} className="space-y-1">
                        <div
                          className={`rounded-lg px-4 py-3 ${
                            isUser ? "bg-primary/10 ml-12" : "mr-12 bg-muted/50"
                          }`}
                        >
                          <p className="text-xs text-muted-foreground">{msg.role}</p>
                          <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                        </div>
                        {msg.human_decision ? (
                          <div className="mr-12 rounded border border-yellow-500/40 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-700 dark:text-yellow-300">
                            {t.devflow.humanDecision}: {(msg.human_decision as any)?.question || "(no question)"}
                          </div>
                        ) : null}
                        {msg.conversation_continuation ? (
                          <div className="mr-12 rounded border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-xs text-blue-700 dark:text-blue-300">
                            {t.devflow.conversationContinuation}: {(msg.conversation_continuation as any)?.reason || ""}
                          </div>
                        ) : null}
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            <div className="border-t px-4 py-3">
              <div className="mx-auto max-w-3xl">
                <div className="flex gap-2">
                  <Textarea
                    placeholder={t.devflow.chatPlaceholder}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    disabled={isLoading || activeSession.session.status !== "active"}
                    className="min-h-[48px] resize-none"
                  />
                  {isLoading ? (
                    <Button variant="destructive" size="icon" onClick={() => setIsLoading(false)}>
                      <StopCircleIcon className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button
                      size="icon"
                      onClick={handleSend}
                      disabled={!inputValue.trim() || activeSession.session.status !== "active"}
                    >
                      <SendIcon className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {showAgentPicker ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-lg">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">{t.devflow.selectAgent}</CardTitle>
                <Button size="sm" variant="ghost" onClick={() => setShowAgentPicker(false)}>
                  ×
                </Button>
              </div>
              <CardDescription>{t.devflow.selectAgentPrompt}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[60vh] overflow-y-auto">
              {agents.map((a) => (
                <button
                  key={a.name}
                  className="flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-accent"
                  onClick={() => handleStartChat(a.name)}
                >
                  <BotIcon className="mt-0.5 h-5 w-5 text-primary" />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium">{a.name}</p>
                    <p className="line-clamp-2 text-xs text-muted-foreground">{a.description}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                      <Badge variant="outline" className="px-1 py-0">
                        {a.history_access}
                      </Badge>
                      <Badge variant="secondary" className="px-1 py-0">
                        {a.skill_count} skills
                      </Badge>
                    </div>
                  </div>
                </button>
              ))}
              {agents.length === 0 ? (
                <p className="text-sm text-muted-foreground">未发现可用的 Agent</p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {/* Right Panel - File Tree */}
      <div className="flex w-64 flex-col border-l">
        {fileView ? (
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b px-3 py-2">
              <span className="truncate text-sm font-medium">{fileView.name}</span>
              <button
                className="rounded px-2 py-1 text-xs hover:bg-accent"
                onClick={() => setFileView(null)}
              >
                关闭
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-3 text-xs">{fileView.content}</pre>
          </div>
        ) : (
          <FileTree
            workspaceName={workspaceName}
            workspacePath={workspacePath}
            workspaceId={workspaceId}
            onFileClick={handleFileClick}
          />
        )}
      </div>
    </div>
  );
}