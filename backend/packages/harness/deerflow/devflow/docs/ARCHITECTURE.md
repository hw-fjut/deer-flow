# DevFlow 架构设计文档

## 1. 系统概述

DevFlow 是基于 DeerFlow 多 Agent 架构的代码全流程开发系统。它实现了从需求分析到代码部署的完整自动化流程，通过主 Agent 编排多个专业子 Agent 协作完成软件开发任务。

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 UI 层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ DevFlowDialog│  │ DevFlowPanel │  │ Hooks/State Mgmt │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         └─────────────────┼──────────────────┬─┘            │
└───────────────────────────┼──────────────────┼──────────────┘
                            │ HTTP/SSE        │
┌───────────────────────────┼──────────────────┼──────────────┐
│                      后端 API 层             │              │
│  ┌──────────────┐  ┌─────▼────────┐  ┌──────▼──────────┐  │
│  │ /api/devflow │  │ Router       │  │ Schemas         │  │
│  │   /run       │  │ (router.py)  │  │ (schemas.py)    │  │
│  └──────────────┘  └─────┬────────┘  └─────────────────┘  │
│                          │                                 │
└──────────────────────────┼─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│                    业务逻辑层                                │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                DevFlowOrchestrator                    │ │
│  │  ┌─────────────────────────────────────────────────┐ │ │
│  │  │ 1. 创建项目 → 2. 启动流水线 → 3. 执行各阶段     │ │ │
│  │  └─────────────────────────────────────────────────┘ │ │
│  └─────────────────────┬─────────────────────────────────┘ │
│                        │ 调度                               │
│  ┌─────────────────────▼─────────────────────────────────┐ │
│  │                    子Agent层                            │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │ │
│  │  │Requirements│Architecture│Development│ Testing   │ │ │
│  │  │  Agent   │   Agent    │   Agent   │   Agent  │ │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │ │
│  │  ┌──────────┐                                        │ │
│  │  │Deployment│                                        │ │
│  │  │  Agent   │                                        │ │
│  │  └──────────┘                                        │ │
│  └───────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│                    数据持久层                                │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                  MemoryService                         │ │
│  │  ┌──────────────┐  ┌──────────────────────────────┐  │ │
│  │  │ FileStorage  │  │ ProjectMemory/StageArtifact  │  │ │
│  │  └──────────────┘  └──────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

## 3. 核心模块

### 3.1 主Agent (DevFlowOrchestrator)

**职责**:
- 创建项目并初始化流水线状态
- 按顺序调度各子Agent执行
- 管理阶段间的数据流转
- 流式返回执行进度

**关键接口**:
```python
async def start_pipeline(name, description) -> PipelineState
async def execute_pipeline(project_id) -> AsyncGenerator[dict]
async def get_pipeline_status(project_id) -> PipelineState
```

### 3.2 子Agent

| Agent | 阶段 | 职责 |
|-------|------|------|
| RequirementsAgent | requirements | 分析需求，生成PRD |
| ArchitectureAgent | architecture | 设计技术架构 |
| DevelopmentAgent | development | 实现代码逻辑 |
| TestingAgent | testing | 编写和执行测试 |
| DeploymentAgent | deployment | 配置和执行部署 |

**基类接口**:
```python
class BaseSubAgent:
    async def execute(self, input: AgentInput) -> AgentOutput
    def get_system_prompt(self, context) -> str
```

### 3.3 项目记忆系统

**职责**:
- 持久化存储各阶段产出物
- 维护项目开发上下文
- 支持跨Agent数据共享

**数据模型**:
```python
class ProjectMemory:
    project_id: str
    name: str
    description: str
    current_stage: str
    artifacts: list[StageArtifact]
    context: dict

class StageArtifact:
    project_id: str
    stage: str
    name: str
    content: str
    files: list[str]
```

## 4. 接口规范

### 4.1 后端API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/devflow/run` | POST | 启动流水线 |
| `/api/devflow/run/{id}/execute` | POST | 执行流水线 (SSE) |
| `/api/devflow/run/{id}/status` | GET | 获取状态 |
| `/api/devflow/projects` | GET | 项目列表 |

### 4.2 SSE事件格式

```json
{"type": "stage_start", "project_id": "...", "stage": "requirements", "timestamp": "..."}
{"type": "stage_complete", "project_id": "...", "stage": "requirements", "output": "...", "timestamp": "..."}
{"type": "stage_failed", "project_id": "...", "stage": "requirements", "error": "...", "timestamp": "..."}
{"type": "pipeline_complete", "project_id": "...", "status": {...}, "timestamp": "..."}
{"type": "pipeline_error", "project_id": "...", "error": "...", "timestamp": "..."}
```

## 5. 扩展指南

### 5.1 添加新子Agent

1. 在 `agents/` 下创建新Agent目录
2. 继承 `BaseSubAgent` 并实现 `execute()` 和 `get_system_prompt()`
3. 在 `orchestrator.py` 的 `_get_agent_for_stage()` 中注册
4. 在 `state.py` 的 `PipelineStage` 枚举中添加新阶段

### 5.2 替换LLM调用

当前使用模拟输出，实际使用时需替换为真实LLM调用：
```python
# 在 agent.py 中替换 _analyze_requirements 等方法
from deerflow.models import create_chat_model

model = create_chat_model(name="gpt-4")
response = await model.ainvoke([SystemMessage(content=prompt), HumanMessage(content=task)])
```

## 6. 文件结构

```
backend/packages/harness/devflow/
├── main_agent/
│   ├── orchestrator.py    # 主Agent编排逻辑
│   ├── prompt.py          # 主Agent提示词
│   └── state.py           # 状态定义
├── agents/
│   ├── base.py            # 子Agent基类
│   ├── requirements/
│   ├── architecture/
│   ├── development/
│   ├── testing/
│   └── deployment/
├── memory/
│   ├── models.py          # 数据模型
│   ├── storage.py         # 存储接口
│   ├── file_storage.py    # 文件存储实现
│   └── service.py         # 记忆服务
├── api/
│   ├── router.py          # API路由
│   └── schemas.py         # 请求/响应模型
└── common/
    ├── config.py          # 配置管理
    ├── exceptions.py      # 异常定义
    └── logging.py         # 日志配置
```
