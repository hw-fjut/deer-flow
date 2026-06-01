"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { getStageIcon, getStageLabel, useDevFlow } from "@/core/devflow";
import { PIPELINE_STAGES } from "@/core/devflow/types";

import { DevFlowDialog } from "./devflow-dialog";

export function DevFlowPanel() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const {
    projectId,
    status,
    currentStage,
    completedStages,
    error,
    isExecuting,
    startPipelineRun,
    executePipelineRun,
    stopExecution,
    reset,
  } = useDevFlow();

  const handleStart = useCallback(
    async (name: string, description: string) => {
      try {
        const response = await startPipelineRun(name, description);
        await executePipelineRun(response.project_id);
      } catch {
        // Error handled in hook
      }
    },
    [startPipelineRun, executePipelineRun]
  );

  const getProgress = () => {
    if (!projectId) return 0;
    return (completedStages.length / PIPELINE_STAGES.length) * 100;
  };

  const getStatusColor = () => {
    switch (status) {
      case "running":
        return "bg-blue-500";
      case "completed":
        return "bg-green-500";
      case "failed":
        return "bg-red-500";
      default:
        return "bg-gray-500";
    }
  };

  if (!projectId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>代码全流程开发</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center gap-4 p-6">
          <div className="text-center text-muted-foreground">
            启动自动化代码开发流程，从需求分析到部署一站式完成
          </div>
          <Button onClick={() => setDialogOpen(true)}>新建开发项目</Button>
        </CardContent>

        <DevFlowDialog open={dialogOpen} onOpenChange={setDialogOpen} onSubmit={handleStart} />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle>开发流程</CardTitle>
          <div className="flex items-center gap-2">
            <div className={`h-2 w-2 rounded-full ${getStatusColor()}`} />
            <span className="text-sm text-muted-foreground">{status}</span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Progress */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>进度</span>
            <span>{Math.round(getProgress())}%</span>
          </div>
          <Progress value={getProgress()} />
        </div>

        {/* Stages */}
        <div className="space-y-2">
          {PIPELINE_STAGES.map((stage, index) => {
            const isCompleted = completedStages.some((s) => s.stage === stage.name);
            const isCurrent = currentStage === stage.name;
            const isPending = !isCompleted && !isCurrent;

            return (
              <div key={stage.name} className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-lg">
                  {getStageIcon(stage.name)}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium">{getStageLabel(stage.name)}</div>
                  <div className="text-xs text-muted-foreground">{stage.description}</div>
                </div>
                {isCompleted && <Badge variant="secondary">完成</Badge>}
                {isCurrent && isExecuting && <Badge variant="default">进行中</Badge>}
                {isPending && <Badge variant="outline">等待</Badge>}
              </div>
            );
          })}
        </div>

        <Separator />

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          {isExecuting ? (
            <Button variant="destructive" onClick={stopExecution} className="flex-1">
              停止执行
            </Button>
          ) : status === "completed" ? (
            <Button onClick={reset} className="flex-1">
              新建项目
            </Button>
          ) : status === "failed" ? (
            <Button onClick={reset} className="flex-1">
              重试
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
