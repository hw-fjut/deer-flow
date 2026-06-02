# DevFlow 全流程工作流指南

> 本文件是 DevFlow 多子 agent 协作流水线的**总体设计文档**。它给出
> 阶段划分与衔接规则、各子 agent 的输入输出规范、循环子图触发与终止
> 机制、两种人类交互场景的识别与处理流程、agent 调用配置文件格式、
> 历史信息访问权限矩阵，以及异常处理与错误恢复机制。
>
> 代码位置：`backend/packages/harness/deerflow/devflow/`

---

## 0. 设计原则

1. **关注点分离** - 每个子 agent 只负责一个明确阶段，agent 之间通过
   *上下文产物（artifact）* 协作，不共享中间状态。
2. **线性头部 + 循环子图** - 需求分析（已合并架构）、前端设计是确
   定性的，只运行一次；spec→测试→部署是开发循环，可迭代。
3. **信息隔离** - 循环子图中的 agent 只看到"前端设计产物"以及"上一次
   循环迭代的产物"。它们看不到需求分析、前端设计的对话历史。
4. **可定制性** - 整个系统通过修改 `agents/<name>/config.md` 与
   `agents/<name>/skills/*.md` 完成定制，无需修改 Python 代码。
5. **人类可介入、可暂停、可恢复** - 子 agent 在任一阶段都可以向人类
   请求决策（Type-1）或开启一段对话（Type-2），由编排器统一调度。

---

## 1. 流程阶段划分与衔接规则

### 1.1 阶段总览

```
                        +---------------- 线性头部 (单次执行) ----------------+
                        |                                                   |
                        v                                                   v
              +-------------+   +-------------+   +-----------------+        |
              | requirements|-->| architecture|-->| frontend_design |        |
              +-------------+   +-------------+   +-----------------+        |
                                                          |                  |
                                                          v                  |
                                            +--------- 循环子图 ----------+  |
                                            |  +---------------------+   |  |
                                            |  | spec_development    |   |  |
                                            |  +---------------------+   |  |
                                            |            |              |  |
                                            |            v              |  |
                                            |  +---------------------+   |  |
                                            |  | code_testing        |   |  |
                                            |  +---------------------+   |  |
                                            |            |              |  |
                                            |            v              |  |
                                            |  +---------------------+   |  |
                                            |  | deployment          |   |  |
                                            |  +---------------------+   |  |
                                            |            |              |  |
                                            |     <-- tests pass +     |  |
                                            |         deploy ok ?      |  |
                                            |            |              |  |
                                            |   no -> 重试 (iter+1)     |  |
                                            |   yes -> 退出             |  |
                                            +---------------------------+  |
                                                                          |
                                                       pipeline_complete <--+
```

### 1.2 衔接规则

| 上游阶段          | 下游阶段                | 衔接契约                                                                                  |
|-------------------|-------------------------|-------------------------------------------------------------------------------------------|
| 启动              | requirements            | 编排器在 `start_pipeline` 中创建 `PipelineState`，并把 `name/description` 写入 `context`  |
| requirements      | frontend_design         | 编排器把 `requirements` 产物 (PRD.md + ARCHITECTURE.md) 作为 `previous_artifacts` 传入     |
| frontend_design   | spec_development (loop) | 编排器构造 `frontend_design_only` 上下文，仅含前端设计产物                                 |
| spec_development  | code_testing (loop)     | 编排器构造 `frontend_design_and_spec` 上下文，含前端设计 + spec 产物                       |
| code_testing      | deployment (loop)       | 编排器构造 `frontend_design_and_testing` 上下文，含前端设计 + 测试产物                     |
| 任何阶段          | 人类决策（暂停）        | 子 agent 设置 `AgentOutput.human_decision`，编排器 yield `human_decision_required` 后停止 |
| 任何阶段          | 对话延续（不暂停）      | 子 agent 设置 `AgentOutput.conversation_continuation`，编排器 yield 该事件并继续          |
| 循环子图          | 退出条件                | `tests_passed && deployment_validated` ∨ `max_iterations` ∨ 人类干预                       |

### 1.3 阶段执行约束

* **串行执行** - 同一时间只运行一个 stage；编排器在协程中按顺序驱动。
* **无回退** - 线性阶段不会回退；循环子图整体重试，但不会回到线性头部。
* **幂等保存** - 每个 stage 的产物保存到 `MemoryService`，key = `project_id + stage`。
  同一 stage 第二次运行会覆盖旧产物，便于循环子图重试时更新产物。

---

## 2. 各子 Agent 输入输出规范

> 通用约定：所有 agent 接受 `AgentInput`、返回 `AgentOutput`。上下文过滤
> 完全由编排器负责，agent 本身不能扩大自己的可见范围。

### 2.1 线性头部

#### 2.1.1 `requirements` (RequirementsAnalysisAgent) — **合并了原架构阶段**

* **输入 (AgentInput.task)**: 用户原始需求描述
* **输入 (AgentInput.context)**: `policy=full`，含项目名/描述/历史对话
* **输入 (AgentInput.previous_artifacts)**: 空
* **输出 (AgentOutput.result)**: **合并的 PRD + 架构文档** 文本
* **输出文件**:
  * `PRD.md` - 摘要、用户角色、MoSCoW 优先级、验收标准
  * `ARCHITECTURE.md` - 技术栈、组件图、API 风格、部署拓扑
* **责任边界**:
  * 产出可衡量的功能/非功能需求
  * 同步产出对应的技术架构（"什么 + 怎么"一次性给出）
  * 不写代码、不产出具体实现
* **不负责**:
  * 写代码
  * 选库版本细节

#### 2.1.2 `frontend_design` (FrontendDesignAgent)

* **输入 (AgentInput.task)**: "执行 frontend_design 阶段"
* **输入 (AgentInput.context)**: `policy=full`，含 `requirements` 产物（PRD + 架构）
* **输入 (AgentInput.previous_artifacts)**: `{"requirements": {content, files, ...}}`
* **输出 (AgentOutput.result)**: 前端设计包文本
* **输出文件**:
  * `design_tokens.md` - 设计 tokens（颜色/字体/间距/动效）
  * `page_blueprints.md` - 页面蓝图（路由、布局、依赖、空/加载/错误态）
  * `component_inventory.md` - 组件清单（原子/分子/有机体/模板）
  * `routing_and_state.md` - 路由树 + 全局状态切片
  * `api_contract_summary.md` - 后端 API 契约摘要
* **责任边界**:
  * 把需求+架构翻译成前端可实现的契约
  * 明确列出"前端要调用什么后端 API"——这是循环子图唯一的输入契约
  * **不写代码、不出测试、不出部署产物**

### 2.2 循环子图

#### 2.2.1 `spec_development` (SpecDevelopmentAgent)

* **输入 (AgentInput.task)**: "执行 spec_development 阶段"
* **输入 (AgentInput.context)**: `policy=frontend_design_only`
  * `artifacts.frontend_design` - 前端设计包
  * `previous_iteration.test_report` - 上一次循环的测试报告（若有）
  * `loop_iteration` / `loop_history` - 循环元数据
* **输入 (AgentInput.previous_artifacts)**: `{"frontend_design": {...}}`
* **输出 (AgentOutput.result)**: 形式化技术规范
* **输出文件**:
  * `api_specs.md` - 完整 OpenAPI 3.1 规范
  * `data_models.md` - 数据模型（含索引/约束/迁移）
  * `interfaces.md` - 服务/仓储接口契约
  * `state_machines.md` - 状态机定义
* **责任边界**:
  * 把前端设计包翻译成可被测试、可被部署的实现规范
  * **不写测试代码、不写部署脚本**
  * 必须为每个端点给出错误模型

#### 2.2.2 `code_testing` (CodeTestingAgent)

* **输入 (AgentInput.task)**: "执行 code_testing 阶段"
* **输入 (AgentInput.context)**: `policy=frontend_design_and_spec`
  * `artifacts.frontend_design`
  * `artifacts.spec_development`
* **输入 (AgentInput.previous_artifacts)**: `{"frontend_design": ..., "spec_development": ...}`
* **输出**: 单元/集成/E2E 测试、覆盖率报告
* **输出文件**:
  * `tests/test_*.py` 等
  * `coverage_report.html`
  * **测试报告文本** 包含 `all tests passed` / `coverage: NN%` 等 marker
* **责任边界**:
  * 至少达到 80% 覆盖率
  * 失败时必须给出失败信息（orchestrator 解析失败原因决定重试）
  * 不允许 `skip` 任何测试

#### 2.2.3 `deployment` (DeploymentAgent)

* **输入 (AgentInput.task)**: "执行 deployment 阶段"
* **输入 (AgentInput.context)**: `policy=frontend_design_and_testing`
  * `artifacts.frontend_design`
  * `artifacts.code_testing`
* **输入 (AgentInput.previous_artifacts)**: `{"frontend_design": ..., "code_testing": ...}`
* **输出**: 部署清单 + 部署报告
* **输出文件**:
  * `Dockerfile`
  * `docker-compose.yml`
  * `.github/workflows/ci.yml`
  * `k8s/deployment.yaml`
  * `DEPLOYMENT.md`
  * **部署报告文本** 包含 `successfully deployed` / `deployment_validated: true` 等 marker
* **责任边界**:
  * 给出可独立运行的部署产物
  * 必须包含 healthcheck
  * 部署报告中的 marker 决定循环子图是否退出

---

## 3. 循环子图：触发条件与终止机制

### 3.1 触发条件

循环子图在前端设计阶段完成后**自动触发**，由 `DevFlowOrchestrator.execute_pipeline`
在 `for stage in LINEAR_STAGES` 完成后调用 `_run_loop_subgraph` 启动。

### 3.2 子图执行流程

```
loop_iteration = 0
while loop_iteration < max_loop_iterations:
    loop_iteration += 1
    state.start_loop_iteration()
    for stage in [spec, test, deploy]:
        agent_result = await execute_stage(stage)
        if agent_result.human_decision:
            pause pipeline, exit reason = HUMAN_DECISION
        if agent_result.conversation_continuation:
            emit event, keep going (if not escalated)
        if not agent_result.success:
            pause pipeline, exit reason = STAGE_FAILED
        state.mark_loop_stage_completed(stage)
    if test_passed AND deployment_validated:
        exit reason = TESTS_PASSED, return
    if loop_iteration >= max_loop_iterations:
        exit reason = MAX_ITERATIONS, return
    emit loop_retry, reset loop_stages_completed, continue
```

### 3.3 终止机制一览

| 触发条件                                          | ExitReason         | 流水线状态       | 下一步                         |
|---------------------------------------------------|--------------------|------------------|--------------------------------|
| `test_passed && deployment_validated`             | `tests_passed`     | `COMPLETED`      | emit `pipeline_complete`        |
| `loop_iteration >= max_loop_iterations`           | `max_iterations`   | `FAILED`         | 等待用户介入或升级到 Type-1 决策 |
| 子 agent 设置 `human_decision`                    | `human_decision`   | `WAITING_HUMAN_DECISION` | 用户提交答案后恢复     |
| 子 agent 的 Type-2 预算耗尽                       | `escalated`        | `WAITING_HUMAN_DECISION` | 自动转 Type-1 请求   |
| 用户调用 `cancel_pipeline`                        | `pipeline_cancelled` | `FAILED`        | 停止                            |
| 子 agent 返回 `success=False`                     | (在 stage 中)      | `FAILED`         | emit `stage_failed` + `pause`   |

### 3.4 成功/失败判定

`DevFlowOrchestrator` 内部两个判定函数：

* `_is_test_report_green(content)` - 检测 "all tests passed"、"0 failed"、
  `coverage: NN%`（>= 80）等 marker
* `_is_deployment_valid(content)` - 检测 "successfully deployed"、
  "deployment_validated: true" 等 marker

子类可通过继承 `DevFlowOrchestrator` 并覆盖这两个方法自定义判定规则。

---

## 4. 人类交互场景：识别标准与处理流程

DevFlow 支持两种人类交互场景，由不同模块管理，互不冲突。

### 4.1 Type-1 - 需人类决策

#### 4.1.1 识别标准

当子 agent 遇到以下情况时，应**立即**发出 Type-1 决策请求：

* 需要在两个/多个互斥方案之间做不可逆选择（如选数据库、选 IdP、选支付服务商）
* 缺少关键约束无法继续（如 "未指明 SLA 等级"）
* 即将做高代价的更改（如 "删除已有数据表"）

#### 4.1.2 标准化请求模板

每个请求都是一个 `HumanDecisionRequest` 对象（见
`common/human_decision.py::HumanDecisionManager`），通过 markdown 渲染后
直接发给前端：

```markdown
## Human Decision Required

**Stage:** <当前阶段>
**Question:** <一句话的问题>
**Deadline:** <ISO 时间戳>
**Decision ID:** `dec-XXXXXXXX`

### Background
<完整的背景说明，让用户能独立做出判断>

### Impact of the Decision
<如果用户选了推荐选项，会发生什么>

### Related Artifacts
`<文件1>`, `<文件2>`

### Options

- **<label1>** **[RECOMMENDED]**
  <description1>
  - impact: <影响说明>
- **<label2>**
  <description2>
  - impact: <影响说明>

**Agent Recommendation:** <label1>

Reply with the option label to continue the pipeline.
```

字段强制约束：

| 字段                | 约束                                                                  |
|---------------------|-----------------------------------------------------------------------|
| `id`                | `dec-` 前缀 + 8 位短哈希                                                |
| `question`          | 单句、问号结尾                                                          |
| `background`        | 至少 1 段（>= 80 字符），让非相关人员也能理解                              |
| `options`           | 2-4 个，每项含 `label` + `description`；label 必须唯一                     |
| `recommended_option`| 必须是 `options` 之一的 label                                              |
| `deadline`          | ISO 时间戳，默认 24h                                                     |
| `impact`            | 至少 1 句话，说明选推荐选项后会发生什么                                      |
| `related_artifacts` | 至少 0 个，必须是已经存在的文件名                                            |

#### 4.1.3 处理流程

```
sub-agent 构造 HumanDecisionRequest
         |
         v
HumanDecisionManager.create_decision_request(...)
         |
         v
返回 AgentOutput(human_decision=<payload>)
         |
         v
编排器 yield `human_decision_required` 事件给前端
         |
         v
前端显示决策卡片；用户选择答案 → POST /api/devflow/run/{id}/decisions
         |
         v
HumanDecisionManager.resolve_decision(decision_id, answer)
         |
         v
编排器重新执行 (resolve 后从断点继续) → emit 后续 stage_* 事件
```

如果用户**没有在 deadline 前回答**：
* `check_timeouts()` 会在下一次被调用时把请求标记为 `TIMEOUT`
* `apply_timeout_fallback()` 自动采用 `recommended_option` 并恢复流水线
* 这避免了"卡住"的流水线

### 4.2 Type-2 - 非决策性对话延续

#### 4.2.1 识别标准

当子 agent 出现以下情况时，应开启一段 Type-2 对话（**而非 Type-1 决策**）：

* 需要**继续澄清**已有信息（"你说的 '高可用' 是 99.9% 还是 99.99%？"）
* 想要**确认**当前思路是否正确（"我打算用 PostgreSQL 15 + pgbouncer，是否 OK？"）
* 想**分享部分产物**让用户先看（"我已经生成了 3 个端点的契约，先看看？"）
* **没有**不可逆的、必须立刻做的选择

#### 4.2.2 自动对话状态机

由 `ConversationStateManager`（`common/conversation_state.py`）实现：

```
                  start_conversation()
                          |
                          v
                  task_status = in_progress
                          |
                          v
                request_continuation()
                          |
              +-----------+-----------+
              | count < max            | count >= max
              v                        v
        count += 1              task_status = blocked
              |                escalated decision
              v                created (Type-1)
        agent.append_message
              |
              v
       user posts message
              |
              v
      count < max ?  -yes-> loop back to request_continuation
                     -no -> blocked -> escalate
```

#### 4.2.3 处理流程

1. 子 agent 调用 `manager.start_conversation(agent, stage, trigger, ...)`
2. 用户在前端看到对话气泡 → 自由输入
3. 子 agent 每次需要追问时调用 `manager.request_continuation(...)`：
   * 若 `count < max_continuations`，返回 `(True, state)`，子 agent 继续
   * 若 `count >= max_continuations`，返回 `(False, state)`，子 agent
     **必须**调用 `request_human_decision` 升级为 Type-1 请求
4. 用户消息通过 `POST /api/devflow/run/{id}/conversations/{cid}/messages`
   写入历史

#### 4.2.4 触发原因分类

`ConversationTrigger` 枚举值：

| Trigger                    | 场景                                                  |
|----------------------------|-------------------------------------------------------|
| `clarification`            | 需要用户澄清已有需求                                    |
| `additional_context`       | 需要用户提供新的上下文                                  |
| `confirm_approach`         | 提议方案让用户确认                                      |
| `incomplete_task`          | 当前任务未完成，需要更多信息                              |
| `partial_output_review`    | 把已完成的部分产物先发给用户预览                          |
| `other`                    | 兜底分类                                               |

### 4.3 两种场景的差异

| 维度           | Type-1 决策                | Type-2 对话                 |
|----------------|----------------------------|-----------------------------|
| 触发后流水线   | 暂停                       | 继续运行                    |
| 用户响应形式   | 从预设选项中选一个           | 自由文本                    |
| 数量上限       | 不限（每次独立）             | `max_continuations` (默认 3)|
| 升级条件       | 无（一次性解决）             | 计数耗尽 → 自动升级 Type-1  |
| 状态机         | pending → answered/timeout  | in_progress → completed/blocked |
| 适用模块       | `human_decision.py`         | `conversation_state.py`     |

---

## 5. Agent 调用配置文件格式说明

DevFlow 通过 **`agents/<name>/config.md`** 与
**`agents/<name>/skills/*.md`** 实现完全可定制。两个文件格式一致。

### 5.1 文件 frontmatter schema

最小化 YAML 子集（仅支持以下结构）：

```yaml
---
name: <string>            # 文件名 / 技能名（可选，与文件名一致即可）
description: <string>     # 必填：给编排器和 LLM 看的简短描述
tools: [tool1, tool2]     # 选填：声明该 agent/skill 可调用的工具
constraints: [rule1, rule2] # 选填：硬约束（用于 system prompt）
output_format: markdown   # 选填：默认 markdown，可为 "json" 等
history_access: <policy>  # 选填，仅 config.md：full / frontend_design_only /
                          #         frontend_design_and_spec / frontend_design_and_testing
allowed_stages: [stage1]  # 选填，仅 config.md：声明此 agent 能跑的阶段
---
```

约束：

* 顶层只支持 `key: value` 与 `key: [a, b]`
* 不支持嵌套 map 与复杂 YAML 语法
* 字符串不需要引号（除非含 `:` 或 `,`）

### 5.2 `config.md` 示例

`agents/frontend_design/config.md`：

```markdown
---
name: frontend_design
description: Frontend Design Agent - produces the design package consumed by the iterative spec/test/deploy loop.
history_access: full
allowed_stages: [frontend_design]
tools: [file_write, file_read, markdown_parse, image_search, present_file]
constraints: [no_backend_implementation, output_must_be_markdown, no_more_than_5_files]
output_format: markdown
---

# Frontend Design Agent

...
```

### 5.3 `skills/<skill>.md` 示例

`agents/spec_development/skills/spec_api_design.md`：

```markdown
---
name: spec_api_design
description: Author the OpenAPI 3.1 specification for all endpoints
tools: [file_write, file_read, markdown_parse]
constraints: [version_path_prefixed, error_model_uniform, every_endpoint_listed]
output_format: markdown
---

# Spec API Design Skill

...
```

### 5.4 加载行为

* `SkillConfigLoader.load_agent_scope(name)` 把 `config.md` 的元数据与
  `skills/*.md` 的元数据合并，输出一个 `AgentSkillScope` 对象
* `BaseSubAgent.render_skill_prompt()` 把 skills 块渲染为 system prompt
* 调 `POST /api/devflow/skills/reload` 可在运行时热重载（无需重启进程）

### 5.5 定制流程

要新增或修改一个 agent，**只需要**：

1. 编辑 `agents/<name>/config.md` - 调整 description / tools / 历史访问策略
2. 编辑/新增 `agents/<name>/skills/<skill>.md` - 调整具体行为
3. （可选）`POST /api/devflow/skills/reload` 让运行时立刻生效

不需要修改任何 Python 文件。

---

## 6. 历史信息访问权限矩阵

| 阶段                  | 用户任务 | 项目元信息 | 对话历史 | requirements | frontend_design | spec_development | code_testing | deployment | 上次循环产物 |
|-----------------------|----------|-----------|----------|--------------|-----------------|------------------|--------------|------------|--------------|
| `requirements`        | ✅        | ✅         | ✅        | -            | -               | -                | -            | -          | -            |
| `frontend_design`     | ✅        | ✅         | ✅        | ✅            | -               | -                | -            | -          | -            |
| `spec_development`    | ❌        | ✅         | ❌        | ❌            | ✅              | -                | -            | -          | ✅ (test report) |
| `code_testing`        | ❌        | ✅         | ❌        | ❌            | ✅              | ✅                | -            | -          | ✅            |
| `deployment`          | ❌        | ✅         | ❌        | ❌            | ✅              | ❌                | ✅            | -          | ✅            |

> ✅ = 可见，❌ = 不可见，- = 不存在

* 线性头部 agent 拥有 *full* 访问：它们需要上下文来产出可被循环子图
  消费的契约。
* 循环子图 agent **只看到前端设计包**以及前一个 loop 阶段的产物。这
  是**编排器强制实施**的——agent 代码本身拿不到更多上下文。

矩阵在代码中的实现：

* `DevFlowOrchestrator._build_stage_context(stage, full_context, state)`
  根据 `LOOP_STAGE_ACCESS` 字典决定可见的 `artifacts`
* `BaseSubAgent.get_system_prompt` 接收的是已经过滤过的 `context`，
  它不会再有 raw 对话历史

---

## 7. 异常处理与错误恢复机制

### 7.1 错误分类

`common/recovery.py::ErrorClassifier.classify(exc)` 把任意异常归类为：

| `ErrorKind`            | 触发示例                                  | 默认 `RecoveryAction`        |
|------------------------|-------------------------------------------|------------------------------|
| `agent_execution`      | 子 agent 抛异常                            | `retry_stage`                |
| `tool_execution`       | shell / file_write 失败                    | `retry_tool`                 |
| `memory_storage`       | 磁盘满 / 序列化错误                         | `retry_stage` (重试保存)      |
| `context_too_large`    | 上下文超 token 限制                         | `use_partial_output`         |
| `human_decision_timeout`| 决策超时                                  | `timeout_fallback`           |
| `loop_max_iterations`  | 子图迭代超限                               | `exit_loop`                  |
| `user_cancelled`       | 用户主动取消                                | `fail_pipeline`              |
| `unknown`              | 兜底                                       | `retry_stage`                |

每个 `ErrorClassification` 还有 `severity`（low/medium/high），编排器
可据此决定是直接 `fail_pipeline` 还是 `retry_stage`。

### 7.2 错误恢复手段

#### 7.2.1 重试

```python
from deerflow.devflow.common.recovery import async_retry

@async_retry(max_attempts=2, backoff_seconds=0.1)
async def my_stage():
    ...
```

`async_retry` 在 `retry_on` 指定异常上重试，每次回退 `backoff_seconds * attempt` 秒。

#### 7.2.2 部分产物

子 agent 遇到不可能完成全部任务时，构造一个 `PartialOutput` 并把它
塞进 `AgentOutput.metadata`，编排器会在 `use_partial_output` 路径下
使用它继续推进。

#### 7.2.3 升级为 Type-1 决策

当子 agent 进入"无法自决"状态时（如 spec 太模糊无法生成），通过
`request_human_decision` 升级为决策请求。失败阶段不计入已完成
stages，编排器会暂停流水线等待用户。

#### 7.2.4 错误兜底路径

| 错误类型            | 兜底策略                                                          |
|---------------------|-------------------------------------------------------------------|
| 阶段重试仍失败       | 转 Type-1 决策（"如何继续？"）                                      |
| 上下文超长           | 使用 `PartialOutput` 继续                                            |
| 决策超时            | 自动采用 `recommended_option`                                        |
| 子图迭代耗尽         | 升级 Type-1 决策（"测试仍不通过，是否继续？"）                       |
| 编排器本身崩溃       | `pipeline_error` 事件 + `PipelineState.status=FAILED` 持久化        |

### 7.3 状态持久化

* `PipelineState.mark_failed` / `mark_completed` 都会写入
  `PipelineState.completed_at` 与 `metadata`，便于断点恢复
* `MemoryService.save_stage_artifact` 每次 stage 完成后落盘
* 通过 `GET /api/devflow/run/{id}/status` 随时查看当前状态
* 决策答案到达后，`submit_human_decision` 重新调用 `execute_pipeline`
  从已完成的 stage 之后继续（编排器通过 `get_stage_result` 跳过已完成 stage）

### 7.4 取消机制

* 任何时刻 `POST /api/devflow/run/{id}/cancel` 调用
  `orchestrator.cancel_pipeline(project_id, reason)`
* 编排器把 `loop_exit_reason` 标为 `PIPELINE_CANCELLED`，`status=FAILED`
* 后续 `execute_pipeline` 不会再跑出新事件

---

## 8. 端到端事件流（参考实现）

```
$ curl -N -X POST http://localhost:8000/api/devflow/run/d6ab8083/execute

data: {"type": "stage_start",    "project_id": "d6ab8083", "stage": "requirements"}
data: {"type": "stage_complete", "project_id": "d6ab8083", "stage": "requirements", "files": ["PRD.md"]}
data: {"type": "stage_start",    "project_id": "d6ab8083", "stage": "architecture"}
data: {"type": "stage_complete", "project_id": "d6ab8083", "stage": "architecture", "files": ["ARCHITECTURE.md"]}
data: {"type": "stage_start",    "project_id": "d6ab8083", "stage": "frontend_design"}
data: {"type": "stage_complete", "project_id": "d6ab8083", "stage": "frontend_design", "files": ["design_tokens.md", ...]}
data: {"type": "loop_start",     "project_id": "d6ab8083", "iteration": 1}
data: {"type": "stage_start",    "stage": "spec_development", "iteration": 1}
data: {"type": "stage_complete", "stage": "spec_development", "iteration": 1, "files": ["api_specs.md", ...]}
data: {"type": "stage_start",    "stage": "code_testing",    "iteration": 1}
data: {"type": "stage_complete", "stage": "code_testing",    "iteration": 1, "files": ["tests/...", "coverage_report.html"]}
data: {"type": "stage_start",    "stage": "deployment",      "iteration": 1}
data: {"type": "stage_complete", "stage": "deployment",      "iteration": 1, "files": ["Dockerfile", ...]}
data: {"type": "loop_complete",  "iteration": 1, "reason": "tests_passed"}
data: {"type": "pipeline_complete", "project_id": "d6ab8083"}
```

失败 / 决策 / 重试路径：

```
data: {"type": "stage_complete", "stage": "code_testing", "iteration": 1}
data: {"type": "loop_retry",     "iteration": 1, "test_passed": false, "deployment_validated": false}
data: {"type": "loop_start",     "iteration": 2}
data: {"type": "stage_start",    "stage": "spec_development", "iteration": 2}
...
data: {"type": "human_decision_required", "stage": "deployment", "decision": {...}}
# pause: stream ends; user must POST /decisions to continue
```

---

## 9. 子 agent 责任一览（速查表）

| 阶段                | 责任                                              | 不应该做                                |
|---------------------|---------------------------------------------------|-----------------------------------------|
| requirements        | PRD、优先级、验收标准                                | 写技术栈、选数据库、写代码               |
| architecture        | 系统架构、组件图、API 风格                            | 写代码、写测试、选库版本细节              |
| frontend_design     | 设计 tokens、页面蓝图、组件、路由、后端 API 摘要     | 写业务代码、选具体 UI 库、写测试         |
| spec_development    | OpenAPI、数据模型、接口、状态机                      | 写测试、选语言、选云厂商                 |
| code_testing        | 测试代码、覆盖率、CI 报告                            | 写业务代码、改业务逻辑                   |
| deployment          | Dockerfile、k8s、CI、部署验证                        | 改业务代码、跳过 healthcheck             |

> 责任边界由 `config.md` 的 `constraints` 字段声明；agent 的 system
> prompt 强制遵循。

---

## 10. 测试 / 验证

* `test_e2e.py` - 端到端冒烟测试：跑完整个 pipeline，验证：
  * 所有 agent 正确加载
  * 线性头部按顺序执行
  * 循环子图运行一次后因 `tests_passed` 退出
  * 人类决策模板能生成正确 markdown
  * 对话延续计数耗尽后升级
  * 错误分类器对常见错误分类正确
* `test_loop.py` - 循环子图路径：
  * 测试报告持续失败 → `loop_retry` → `loop_retry_exhausted`
  * 子 agent 抛 Type-1 决策 → 流水线暂停
* `test_chat.py` - 对话模式（Type-3 人类交互）：
  * 5 个 agent 同时启动会话并验证其历史可见范围 policy
  * 验证跨 session 的历史隔离
  * 验证关闭 / 重新打开 / 列出 / 计数语义
  * 验证对关闭的 session 发送消息会抛错
* 启动方法（PowerShell）：
  ```powershell
  cd e:\sourceCode\deer-flow
  python test_e2e.py
  python test_loop.py
  python test_chat.py
  ```

---

## 11. Type-3 人类交互：单 Agent 对话模式（Chat Mode）

> 这是 DevFlow 提供的**第三种**人类交互模式，专门用于"我想直接跟某个
> 特定的 agent 聊一聊"的场景。和流水线模式（"跑完整个 5 阶段"）是
> 正交的：聊天会话与流水线相互独立，可以并存。

### 11.1 与 Type-1 / Type-2 的对比

| 维度              | Type-1 决策               | Type-2 对话延续             | Type-3 单 Agent 对话        |
|-------------------|---------------------------|-----------------------------|-----------------------------|
| 触发方            | 流水线中的子 agent         | 流水线中的子 agent          | 前端用户（不经过流水线）     |
| 流水线状态        | **暂停**                  | 继续运行                    | 不涉及（独立会话）           |
| 范围              | 一个 stage                | 一个 stage                  | 一个**指定**的 agent         |
| 是否经过编排器    | ✅                        | ✅                          | ✅（`chat_with_agent` 入口）|
| 默认可见上下文    | 编排器过滤后的 stage 上下文 | 同上                        | 由该 agent 的 `history_access` 决定 |
| 轮次上限          | 不限（一次性解决）         | `max_continuations=3`       | **不限**                    |
| 与 Type-1/2 兼容  | -                         | -                           | ✅ 一次回复里可以同时携带    |

### 11.2 数据结构

`common/conversation_state.py` 中新增：

* `ChatMessage(role, content, timestamp, metadata, human_decision?, conversation_continuation?)`
  - 持久化对话中的一条消息。`human_decision` 与 `conversation_continuation` 字段
    允许 agent 在同一次回复里同时发起 Type-1 / Type-2 信号。
* `ChatSession(session_id, project_id, agent_name, history_access, status, messages[], ...)`
  - 表示与一个特定 agent 的**独立**多轮会话。
  - `history_access` 在会话创建时从 `config.md` 解析并冻结。
  - `status` ∈ `{"active", "closed"}`，关闭后仍保留历史，可重新打开。
* `ChatSessionManager` - 负责 start / append / list / close / reopen。

### 11.3 编排器入口

`main_agent/orchestrator.py` 提供的方法：

```python
session = await orch.start_chat_session(
    project_id=project_id,
    agent_name="spec_development",
    description="Brainstorm the auth API",
)
# -> ChatSession(session_id, project_id, agent_name, history_access=...)

reply = await orch.chat_with_agent(
    session_id=session.session_id,
    user_message="List 3 endpoints with verbs and paths",
)
# reply = {
#   "session":   <updated ChatSession dict>,
#   "reply":     {"content": ..., "files": [], "success": True, ...},
#   "human_decision":            <Type-1 payload, if any>,
#   "conversation_continuation": <Type-2 payload, if any>,
# }

await orch.close_chat_session(session_id)
await orch.reopen_chat_session(session_id)
sessions = await orch.list_chat_sessions(project_id=..., only_active=True)
detail   = await orch.get_chat_session(session_id)
```

`chat_with_agent` 内部流程：

1. 把 user 消息追加到 `ChatSession.messages`
2. 从 `MemoryService.get_project_context()` 拉取项目元数据 + artifacts
3. 在 `_build_chat_context()` 中按 `history_access` 过滤 artifacts，并注入：
   * `mode: "chat"`
   * `chat_history: <最近 30 条消息>`
4. 用过滤后的 `AgentInput` 调用目标 `agent.execute()`
5. 把 agent 的返回结果（result / human_decision / conversation_continuation）
   追加为一条 `role="agent"` 消息

### 11.4 历史可见范围矩阵（聊天模式）

| 目标 agent         | `history_access` policy  | 聊天时实际可见                                  |
|--------------------|--------------------------|--------------------------------------------------|
| `requirements`     | `full`                   | 全部 artifacts + 项目元信息 + 聊天历史            |
| `frontend_design`  | `full`                   | 全部 artifacts + 项目元信息 + 聊天历史            |
| `spec_development` | `frontend_design_only`   | **仅** `frontend_design` artifact + 聊天历史     |
| `code_testing`     | `frontend_design_and_spec` | `frontend_design` + `spec_development` + 聊天历史 |
| `deployment`       | `frontend_design_and_testing` | `frontend_design` + `code_testing` + 聊天历史 |

> 与流水线模式共享同一套过滤函数，但触发方式不同：流水线中
> `_build_stage_context()` 由编排器根据 `LOOP_STAGE_ACCESS` 自动选用；聊天
> 模式中 `_build_chat_context()` 直接读 `session.history_access`。

### 11.5 API 表面

| Method | Path                                          | 用途                          |
|--------|-----------------------------------------------|-------------------------------|
| POST   | `/api/devflow/chat/{project_id}/sessions`     | 创建 chat session             |
| GET    | `/api/devflow/chat/{project_id}/sessions`     | 列出 chat session（可仅 active）|
| GET    | `/api/devflow/chat/sessions/{session_id}`     | 读取 session + 完整历史       |
| POST   | `/api/devflow/chat/sessions/{session_id}/messages` | 发送消息，返回 agent 回复   |
| DELETE | `/api/devflow/chat/sessions/{session_id}`     | 关闭 session                  |
| POST   | `/api/devflow/chat/sessions/{session_id}/reopen` | 重新打开已关闭 session      |

> 调用顺序示例：
> ```bash
> # 1) 创建 session
> curl -X POST .../api/devflow/chat/$PID/sessions \
>   -d '{"agent_name": "spec_development", "description": "Brainstorm"}'
>
> # 2) 发送消息
> curl -X POST .../api/devflow/chat/sessions/$SID/messages \
>   -d '{"content": "List 3 endpoints"}'
> ```

### 11.6 前端 UI 集成

`frontend/src/components/devflow/chat-page.tsx` 已改造为双模式布局：

* 顶部**模式切换器**（`WorkflowIcon` / `BotIcon`）：在 **流水线模式** 与
  **对话模式** 之间切换
* **流水线模式**沿用原有逻辑：会跑完整个 5 阶段
* **对话模式**新组件：
  * 左侧 `SessionList` - 列出当前项目下所有 active chat session
  * `+ 新建 Agent 对话` 按钮 - 弹出 AgentPicker（调 `GET /api/devflow/skills`）
  * 中间 `ChatArea` - 渲染历史消息，底部 textarea，Enter 发送
  * 右上角 `关闭 / 重新打开` 按钮 - 控制 session 生命周期
  * 显示 `history_access` 与 skill 数量，让用户清楚该 agent 的可见范围

Agent 选择器会展示每个 agent 的 description、history_access policy、skill
数量，用户在选择前就能预知该 agent 看不到什么、擅长什么。

### 11.7 适用场景

| 场景                            | 推荐模式                |
|---------------------------------|-------------------------|
| "给我做一个完整项目"             | 流水线模式              |
| "看一下 specs 里那个端点的错误模型" | 对话模式 + `spec_development` |
| "和 deployment 聊聊 k8s 调优"    | 对话模式 + `deployment`  |
| "现在还不确定需求，再想想"       | 流水线模式（会先卡在 requirements） |
| "中间产物给老板先看看"           | 流水线模式（前端会展示 stage 事件） |

> **重要**：对话模式的回复**不会**写入项目的流水线产物（artifacts）。
> 如果用户希望把对话中的发现回写到 `frontend_design` 之类的产物，仍然
> 需要走流水线模式。对话模式只做"问 - 答"，不污染产物。

