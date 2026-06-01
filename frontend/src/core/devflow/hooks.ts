/** DevFlow React Hooks */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { PipelineResponse, StageEvent } from "./api";
import { executePipeline, getPipelineStatus, startPipeline } from "./api";
import type { PipelineState, PipelineStatus } from "./types";
import { PIPELINE_STAGES } from "./types";

/**
 * Hook for managing DevFlow pipeline execution
 */
export function useDevFlow() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [status, setStatus] = useState<PipelineStatus>("pending");
  const [currentStage, setCurrentStage] = useState<string>("");
  const [completedStages, setCompletedStages] = useState<StageEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  /**
   * Start a new pipeline
   */
  const startPipelineRun = useCallback(async (name: string, description: string) => {
    try {
      setError(null);
      const response: PipelineResponse = await startPipeline({ name, description });
      setProjectId(response.project_id);
      setStatus(response.status as PipelineStatus);
      setCurrentStage(response.current_stage);
      setCompletedStages([]);
      toast.success(`Pipeline started: ${name}`);
      return response;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to start pipeline";
      setError(message);
      toast.error(message);
      throw err;
    }
  }, []);

  /**
   * Execute pipeline and stream events
   */
  const executePipelineRun = useCallback(async (pid: string) => {
    if (isExecuting) return;
    
    setIsExecuting(true);
    setError(null);
    abortRef.current = new AbortController();

    try {
      for await (const event of executePipeline(pid)) {
        if (abortRef.current?.signal.aborted) break;

        switch (event.type) {
          case "stage_start":
            setCurrentStage(event.stage || "");
            toast.info(`Starting stage: ${event.stage}`);
            break;

          case "stage_complete":
            setCompletedStages((prev) => [...prev, event]);
            toast.success(`Completed stage: ${event.stage}`);
            break;

          case "stage_failed":
            setError(event.error || "Stage failed");
            toast.error(`Stage failed: ${event.stage} - ${event.error}`);
            setStatus("failed");
            break;

          case "pipeline_complete":
            setStatus("completed");
            toast.success("Pipeline completed successfully!");
            break;

          case "pipeline_error":
            setError(event.error || "Pipeline error");
            setStatus("failed");
            toast.error(`Pipeline error: ${event.error}`);
            break;
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Execution failed";
      setError(message);
      setStatus("failed");
      toast.error(message);
    } finally {
      setIsExecuting(false);
      abortRef.current = null;
    }
  }, [isExecuting]);

  /**
   * Stop pipeline execution
   */
  const stopExecution = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      toast.info("Pipeline execution stopped");
    }
  }, []);

  /**
   * Load existing pipeline status
   */
  const loadStatus = useCallback(async (pid: string) => {
    try {
      const response = await getPipelineStatus(pid);
      setProjectId(response.project_id);
      setStatus(response.status as PipelineStatus);
      setCurrentStage(response.current_stage);
      setCompletedStages(
        response.completed_stages.map((stage) => ({
          type: "stage_complete",
          project_id: pid,
          stage: stage.stage,
          output: stage.output,
          timestamp: new Date().toISOString(),
        }))
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load status";
      setError(message);
      toast.error(message);
    }
  }, []);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, []);

  return {
    projectId,
    status,
    currentStage,
    completedStages,
    error,
    isExecuting,
    startPipelineRun,
    executePipelineRun,
    stopExecution,
    loadStatus,
    reset: () => {
      setProjectId(null);
      setStatus("pending");
      setCurrentStage("");
      setCompletedStages([]);
      setError(null);
      setIsExecuting(false);
    },
  };
}

/**
 * Get stage label by name
 */
export function getStageLabel(stageName: string): string {
  const stage = PIPELINE_STAGES.find((s) => s.name === stageName);
  return stage?.label || stageName;
}

/**
 * Get stage icon by name
 */
export function getStageIcon(stageName: string): string {
  const stage = PIPELINE_STAGES.find((s) => s.name === stageName);
  return stage?.icon || "📋";
}
