# DevFlow - 全流程代码开发模式

> 基于多子 agent 协作的软件开发流水线。**线性头部**（需求分析已合并
> PRD + 架构 / 前端设计）+ **循环子图**（spec / 测试 / 部署）+ 标准化
> 人类交互层 + 仅通过 `.md` 文件即可定制的技能系统。

## 快速开始

```powershell
cd e:\sourceCode\deer-flow\backend\packages\harness
python -c "import sys; sys.path.insert(0, '.'); from deerflow.devflow.agents import get_agent_registry; print(list(get_agent_registry().keys()))"
```

## 文档索引

| 文档                                                | 用途                                                |
|-----------------------------------------------------|-----------------------------------------------------|
| [`docs/WORKFLOW_GUIDE.md`](./docs/WORKFLOW_GUIDE.md) | **总入口** - 阶段划分、衔接规则、输入输出、循环子图、人类交互、权限矩阵、异常恢复 |
| [`docs/PIPELINE_ARCHITECTURE.md`](./docs/PIPELINE_ARCHITECTURE.md) | 架构细节：事件流、API 表面、SSE 格式、模块映射        |
| [`docs/HUMAN_INTERACTION.md`](./docs/HUMAN_INTERACTION.md) | 两种人类交互场景的识别、处理时序、API、对比          |
| [`docs/SKILL_AUTHORING.md`](./docs/SKILL_AUTHORING.md) | 如何**只修改 `.md` 文件**定制子 agent                |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)     | 早期版本：模块结构、关键类                           |

## 代码结构

```
devflow/
├── main_agent/              # 主Agent核心逻辑
│   ├── orchestrator.py      # 任务编排器（含循环子图）
│   ├── prompt.py            # 主Agent提示词
│   └── state.py             # 流水线状态（含 LoopExitReason 等）
├── agents/                  # 子Agent集合
│   ├── base.py              # 子Agent基类
│   ├── requirements/        # 需求分析 + 架构 Agent（合并）  (linear, history=full)
│   │   ├── config.md
│   │   ├── agent.py
│   │   └── skills/
│   │       ├── prd_authoring.md
│   │       └── architecture_design.md
│   ├── frontend_design/     # 前端设计Agent                (linear, history=full)
│   ├── spec_development/    # Spec开发Agent                (loop,   history=frontend_design_only)
│   ├── code_testing/        # 代码测试Agent                (loop,   history=frontend_design_and_spec)
│   └── deployment/          # 服务部署Agent                (loop,   history=frontend_design_and_testing)
├── memory/                  # 项目记忆系统
│   ├── models.py            # 数据模型
│   ├── storage.py           # 记忆存储
│   └── service.py           # 记忆服务
├── api/                     # 对外API接口
│   └── router.py            # API路由（含决策/对话/技能接口）
└── common/                  # 公共工具
    ├── config.py            # 配置管理
    ├── exceptions.py        # 异常定义
    ├── logging.py           # 日志配置
    ├── human_decision.py    # Type-1 人类决策管理
    ├── conversation_state.py # Type-2 对话状态管理
    ├── skill_config.py      # .md 技能配置加载
    └── recovery.py          # 错误分类/重试/部分产物
```

## 核心概念

* **主Agent** - `DevFlowOrchestrator` 负责任务分解、子 agent 调度、循环
  子图驱动、人类交互协调。
* **5 个子Agent** - 需求（PRD+架构）/ 前端 / spec / 测试 / 部署。
  其行为由 `agents/<name>/config.md` 与 `agents/<name>/skills/*.md` 定义。
* **循环子图** - `spec_development → code_testing → deployment` 持续迭代
  直至测试通过 + 部署验证 / 达到最大迭代次数 / 用户决策。
* **项目记忆** - `MemoryService` 存储各阶段产物，编排器按 *history access
  policy* 过滤后传给子 agent。
* **两种人类交互** - Type-1 决策请求（暂停流水线）+ Type-2 对话延续
  （自动状态追踪，耗尽后升级为 Type-1）。

## 设计选择：需求与架构合并

`requirements` 阶段**同时**产出 PRD 和架构文档（"做什么"和"怎么做"），
由同一个 agent 完成。原因是这两块信息在系统设计中耦合过深：架构选
择直接由需求约束驱动，把它们拆成两个独立阶段会带来大量冗余的上下
文传递，反而增加不一致风险。

## 运行测试

```powershell
cd e:\sourceCode\deer-flow
python test_e2e.py     # 端到端：5 个 agent 全跑一遍，验证循环子图、决策模板、对话升级、错误分类
python test_loop.py    # 循环子图：失败重试 / Type-1 暂停
```
