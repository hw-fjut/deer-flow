"use client";

import { MessageSquarePlusIcon, SendIcon, StopCircleIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { getBackendBaseURL } from "@/core/config";

import type { ChatMessageResponse, ConversationResponse, FileTreeNode } from "@/core/devflow/api";
import {
  createConversation,
  deleteConversation,
  getMessages,
  listConversations,
  readFile,
  sendMessage,
} from "@/core/devflow/api";

import { FileTree } from "./file-tree";

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
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessageResponse[]>([]);
  const [isCreatingConv, setIsCreatingConv] = useState(false);
  const [newConvTitle, setNewConvTitle] = useState("");
  const [fileView, setFileView] = useState<{ name: string; content: string } | null>(null);

  // Load conversations
  useEffect(() => {
    async function load() {
      try {
        const data = await listConversations(workspaceId);
        setConversations(data);
        if (data.length > 0 && !activeConversation) {
          setActiveConversation(data[0].id);
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to load conversations");
      }
    }
    load();
  }, [workspaceId]);

  // Load messages when active conversation changes
  useEffect(() => {
    if (!activeConversation) return;
    async function load() {
      try {
        const data = await getMessages(activeConversation);
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

  const handleDeleteConversation = useCallback(async (id: string) => {
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
  }, [activeConversation]);

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
      // Call the stream endpoint which returns SSE events
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

      // Process SSE stream
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Failed to read response stream");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      try {
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
                
                // Convert pipeline events to chat messages
                let chatMsg: ChatMessageResponse | null = null;
                
                switch (event.type) {
                  case "stage_start":
                    chatMsg = {
                      role: "assistant",
                      content: ` 开始阶段: ${event.stage}`,
                      timestamp: event.timestamp,
                    };
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
                      content: `🎉 DevFlow 流水线完成!\n\n项目ID: ${event.project_id}\n状态: ${event.status?.status || "completed"}`,
                      timestamp: event.timestamp,
                    };
                    break;
                  case "pipeline_error":
                    chatMsg = {
                      role: "assistant",
                      content: ` 流水线执行失败\n\n错误: ${event.error || "未知错误"}`,
                      timestamp: event.timestamp,
                    };
                    break;
                }
                
                if (chatMsg) {
                  setMessages((prev) => [...prev, chatMsg!]);
                }
              } catch {
                // Skip malformed SSE data
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }

      // Update conversation last_message
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeConversation
            ? { ...c, last_message: inputValue.slice(0, 50) }
            : c
        )
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "发送失败";
      toast.error(msg);
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: `错误: ${msg}`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, activeConversation, isLoading, workspaceId]);

  const handleFileClick = useCallback(async (node: FileTreeNode) => {
    try {
      const data = await readFile(workspaceId, node.path);
      setFileView({ name: node.name, content: data.content });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "读取文件失败");
    }
  }, [workspaceId]);

  const activeConv = conversations.find((c) => c.id === activeConversation);

  return (
    <div className="flex h-screen bg-background">
      {/* Left Panel - Conversation List */}
      <div className="flex w-72 flex-col border-r">
        {/* Header */}
        <div className="border-b px-4 py-3">
          <div className="mb-3">
            <h2 className="text-sm font-medium">{workspaceName}</h2>
            <p className="truncate text-xs text-muted-foreground">
              {workspacePath}
            </p>
          </div>
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

        {/* Create Conversation Form */}
        {isCreatingConv && (
          <div className="border-b px-4 py-3">
            <div className="space-y-2">
              <Textarea
                placeholder="会话标题"
                value={newConvTitle}
                onChange={(e) => setNewConvTitle(e.target.value)}
                rows={2}
                className="resize-none"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={handleCreateConversation} className="flex-1">
                  创建
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setIsCreatingConv(false);
                    setNewConvTitle("");
                  }}
                >
                  取消
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Conversation List */}
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
                <p className="truncate text-xs text-muted-foreground">
                  {conv.last_message}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Middle Panel - Chat Area */}
      <div className="flex flex-1 flex-col">
        {/* Chat Header */}
        <div className="flex items-center justify-between border-b px-4 py-2">
          <h3 className="font-medium">{activeConv?.title || "选择一个会话"}</h3>
        </div>

        {/* Messages */}
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

        {/* Input Area */}
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
            <pre className="flex-1 overflow-auto p-3 text-xs">
              {fileView.content}
            </pre>
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
