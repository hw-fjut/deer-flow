# DevFlow - 全流程代码开发模式

基于 DeerFlow 多 Agent 架构的代码全流程开发系统，实现从需求分析到代码开发部署的完整流程。

## 架构设计

```
devflow/
├── main_agent/              # 主Agent核心逻辑
│   ├── orchestrator.py      # 任务编排器
│   ├── prompt.py            # 主Agent提示词
│   └── state.py             # 状态管理
├── agents/                  # 子Agent集合
│   ├── base.py              # 子Agent基类
│   ├── requirements/        # 需求分析Agent
│   ├── architecture/        # 架构设计Agent
│   ├── development/         # 代码开发Agent
│   ├── testing/             # 测试Agent
│   └── deployment/          # 部署Agent
├── memory/                  # 项目记忆系统
│   ├── models.py            # 数据模型
│   ├── storage.py           # 记忆存储
│   └── service.py           # 记忆服务
├── api/                     # 对外API接口
│   ├── router.py            # API路由
│   └── schemas.py           # 请求/响应模型
└── common/                  # 公共工具和配置
    ├── config.py            # 配置管理
    ├── exceptions.py        # 异常定义
    └── logging.py           # 日志配置
```

## 核心概念

- **主Agent**: 负责任务分解、子Agent调度、结果整合
- **子Agent**: 每个阶段的专业Agent（需求、架构、开发、测试、部署）
- **项目记忆**: 存储各阶段产出物，维持上下文连续性
