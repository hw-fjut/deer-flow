/** DevFlow 类型定义 */

export interface PipelineStage {
  name: string;
  label: string;
  icon: string;
  description: string;
}

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    name: "requirements",
    label: "需求分析",
    icon: "📋",
    description: "分析用户需求，生成PRD文档",
  },
  {
    name: "architecture",
    label: "架构设计",
    icon: "🏗️",
    description: "设计技术架构",
  },
  {
    name: "development",
    label: "代码开发",
    icon: "💻",
    description: "实现具体代码逻辑",
  },
  {
    name: "testing",
    label: "测试",
    icon: "🧪",
    description: "编写和执行测试用例",
  },
  {
    name: "deployment",
    label: "部署",
    icon: "🚀",
    description: "配置并执行部署",
  },
];

export type PipelineStatus = "pending" | "running" | "completed" | "failed" | "paused";

export interface StageResult {
  stage: string;
  success: boolean;
  output: string;
  files: string[];
  error?: string;
  startedAt: string;
  completedAt?: string;
  durationSeconds: number;
}

export interface PipelineState {
  projectId: string;
  name: string;
  description: string;
  status: PipelineStatus;
  currentStage: string;
  completedStages: StageResult[];
  failedStage?: StageResult;
  startedAt?: string;
  completedAt?: string;
}

export interface DevFlowProject {
  projectId: string;
  name: string;
  description: string;
  status: PipelineStatus;
  currentStage: string;
}
