"use client";

import { FolderIcon, FolderOpenIcon, PlusIcon, TrashIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/core/i18n/hooks";

import { DevFlowChatPage } from "@/components/devflow/chat-page";
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  type WorkspaceResponse,
} from "@/core/devflow/api";

export default function DevFlowPage() {
  const { t } = useI18n();
  const [workspaces, setWorkspaces] = useState<WorkspaceResponse[]>([]);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [newWorkspacePath, setNewWorkspacePath] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedWorkspace, setSelectedWorkspace] = useState<WorkspaceResponse | null>(null);
  const [hasEntered, setHasEntered] = useState(false);

  useEffect(() => {
    loadWorkspaces();
  }, []);

  const loadWorkspaces = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await listWorkspaces();
      setWorkspaces(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load workspaces";
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleSelectWorkspace = useCallback((workspace: WorkspaceResponse) => {
    setSelectedWorkspace(workspace);
  }, []);

  const handleEnterWorkspace = useCallback(() => {
    if (selectedWorkspace) {
      setHasEntered(true);
    }
  }, [selectedWorkspace]);

  const handleBack = useCallback(() => {
    setHasEntered(false);
    setSelectedWorkspace(null);
  }, []);

  const handleCreateWorkspace = useCallback(async () => {
    if (!newWorkspaceName.trim() || !newWorkspacePath.trim()) return;

    try {
      const workspace = await createWorkspace({
        name: newWorkspaceName.trim(),
        path: newWorkspacePath.trim(),
      });
      setWorkspaces((prev) => [...prev, workspace]);
      setNewWorkspaceName("");
      setNewWorkspacePath("");
      setIsCreating(false);
      toast.success(`工作区 "${workspace.name}" 已创建`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "创建失败";
      toast.error(message);
    }
  }, [newWorkspaceName, newWorkspacePath]);

  const handleDeleteWorkspace = useCallback(async (id: string) => {
    try {
      await deleteWorkspace(id);
      setWorkspaces((prev) => prev.filter((ws) => ws.id !== id));
      setSelectedWorkspace((prev) => (prev?.id === id ? null : prev));
      toast.success("工作区已删除");
    } catch (error) {
      const message = error instanceof Error ? error.message : "删除失败";
      toast.error(message);
    }
  }, []);

  // If user has entered a workspace, show the chat page
  if (hasEntered && selectedWorkspace) {
    return (
      <DevFlowChatPage
        workspaceId={selectedWorkspace.id}
        workspaceName={selectedWorkspace.name}
        workspacePath={selectedWorkspace.path}
        onBack={handleBack}
      />
    );
  }

  // Otherwise show workspace selection
  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Header */}
      <header className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <FolderOpenIcon className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-lg font-semibold">{t.devflow.workspaceTitle}</h1>
              <p className="text-sm text-muted-foreground">
                {t.devflow.workspaceSubtitle}
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Workspace List */}
        <div className="flex w-80 flex-col border-r">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h2 className="text-sm font-medium">{t.devflow.workspaceListTitle}</h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsCreating(!isCreating)}
            >
              <PlusIcon className="h-4 w-4" />
            </Button>
          </div>

          {/* Create Workspace Form */}
          {isCreating && (
            <div className="border-b px-4 py-3">
              <div className="space-y-3">
                <Input
                  placeholder={t.devflow.workspaceNamePlaceholder}
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                />
                <Input
                  placeholder={t.devflow.workspacePathPlaceholder}
                  value={newWorkspacePath}
                  onChange={(e) => setNewWorkspacePath(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={handleCreateWorkspace}
                    disabled={!newWorkspaceName || !newWorkspacePath}
                    className="flex-1"
                  >
                    {t.devflow.create}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setIsCreating(false)}
                  >
                    {t.devflow.cancel}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Workspace Items */}
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                加载中...
              </div>
            ) : workspaces.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <FolderIcon className="h-8 w-8 opacity-50" />
                <p>暂无工作区</p>
                <p className="text-xs">点击上方 + 创建工作区</p>
              </div>
            ) : (
              workspaces.map((workspace) => (
                <div
                  key={workspace.id}
                  className={`group flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors hover:bg-accent ${
                    selectedWorkspace?.id === workspace.id ? "bg-accent" : ""
                  }`}
                  onClick={() => handleSelectWorkspace(workspace)}
                >
                  <FolderIcon className="h-4 w-4 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-medium">
                      {workspace.name}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {workspace.path}
                    </p>
                  </div>
                  <button
                    className="rounded p-1 opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteWorkspace(workspace.id);
                    }}
                  >
                    <TrashIcon className="h-3 w-3" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Panel - Details & Enter */}
        <div className="flex flex-1 items-center justify-center p-8">
          {selectedWorkspace ? (
            <Card className="w-full max-w-md">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FolderOpenIcon className="h-5 w-5" />
                  {selectedWorkspace.name}
                </CardTitle>
                <CardDescription>{t.devflow.confirmEnter}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg bg-muted p-4">
                  <p className="text-sm text-muted-foreground">
                    <span className="font-medium">{t.devflow.pathLabel}</span>
                    {selectedWorkspace.path}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    <span className="font-medium">{t.devflow.dateLabel}</span>
                    {selectedWorkspace.created_at}
                  </p>
                </div>

                <div className="rounded-lg border bg-muted/50 p-4">
                  <h4 className="mb-2 text-sm font-medium">{t.devflow.developmentPipeline}</h4>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span>📋 需求分析</span>
                    <span>→</span>
                    <span>🏗️ 架构设计</span>
                    <span>→</span>
                    <span>💻 代码开发</span>
                    <span>→</span>
                    <span>🧪 测试</span>
                    <span>→</span>
                    <span> 部署</span>
                  </div>
                </div>

                <Button onClick={handleEnterWorkspace} className="w-full">
                  {t.devflow.enterWorkspace}
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="text-center text-muted-foreground">
              <FolderIcon className="mx-auto mb-4 h-12 w-12 opacity-50" />
              <p className="text-sm">{t.devflow.selectWorkspacePrompt}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
