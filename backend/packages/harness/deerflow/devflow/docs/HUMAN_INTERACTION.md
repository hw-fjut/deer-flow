# DevFlow 人类交互场景详解

> 本文件配套 [`WORKFLOW_GUIDE.md`](./WORKFLOW_GUIDE.md) 第 4 章，详细说明
> 两种人类交互场景的识别、处理流程、API 形态与 UI 行为。

---

## 1. 总览

DevFlow 在流水线任意阶段都可能向用户发起交互。共有两种交互：

| 名称              | 模块                                | 是否暂停流水线 | 用户响应形式       |
|-------------------|-------------------------------------|----------------|--------------------|
| Type-1 决策请求   | `common/human_decision.py`          | 是             | 从 2-4 个选项中选一个 |
| Type-2 对话延续   | `common/conversation_state.py`      | 否（直到耗尽） | 自由文本消息       |

两种场景在代码中完全独立，可以由同一个子 agent 在同一任务中**混合使用**：
先开 Type-2 问几个澄清问题，问题没解决就升级为 Type-1。

---

## 2. Type-1：需人类决策

### 2.1 触发判定（什么情况下应该发）

子 agent 在任一阶段遇到下面任意一条**应当**调用 `request_human_decision`：

1. **不可逆选择** - 选数据库、选 IdP、选云厂商、选存储引擎
2. **缺失关键约束** - 性能/合规/安全目标没有指定（如"未说明 SLA 是 99.9 还是 99.99"）
3. **高代价操作** - "删除旧数据表"、"切换到不同的 ORM"
4. **不兼容的方案并存** - "用户登录可走 OAuth2 或 SAML，需要确认"

反例（**不应该**用 Type-1）：

* 写错了字段名 → 改代码即可，不要打扰用户
* 决定类名 → agent 内部决定即可
* 选单元测试框架 → 这是 agent 的责任，不是用户的

### 2.2 标准化模板字段

```python
request = HumanDecisionManager.create_decision_request(
    stage="<当前阶段>",
    question="<单句问题，?结尾>",
    background="<完整背景>=80 字符>",
    options=[
        {"label": "A", "description": "A 是什么"},
        {"label": "B", "description": "B 是什么"},
    ],
    recommended_option="A",
    impact="选 A 会导致 ... ",
    related_artifacts=["ARCHITECTURE.md"],
    timeout_hours=24,
)
```

字段约束（由 `HumanDecisionManager.create_decision_request` 强制）：

| 字段                | 类型        | 约束                                                              |
|---------------------|-------------|-------------------------------------------------------------------|
| `id`                | str         | 自动生成，`dec-XXXXXXXX`                                          |
| `stage`             | str         | 必填，对应当前阶段                                                |
| `question`          | str         | 必填，**单句**且 `?` 结尾                                          |
| `background`        | str         | 必填，>= 80 字符                                                  |
| `options`           | list[dict]  | 必填，2-4 个；每个含 `label`（唯一）+ `description`               |
| `recommended_option`| str \| None | 必须是 `options` 中的某个 label                                    |
| `deadline`          | str         | ISO 时间戳，默认 24h                                              |
| `impact`            | str         | 选填，说明选推荐选项会发生什么                                      |
| `related_artifacts` | list[str]   | 选填，必须是已存在的文件名                                          |

### 2.3 Markdown 渲染样例

```markdown
## Human Decision Required

**Stage:** architecture
**Question:** Which database should we use for the todo app?
**Deadline:** 2026-06-03T12:00:00
**Decision ID:** `dec-a1b2c3d4`

### Background
The PRD requires a small relational store with JSON support.

### Impact of the Decision
PostgreSQL will be added to docker-compose; SQLite is single-node only.

### Related Artifacts
`ARCHITECTURE.md`, `DEPLOYMENT.md`

### Options

- **PostgreSQL** **[RECOMMENDED]**
  Mature RDBMS, JSONB support, easy to host
  - impact: PostgreSQL will be added to docker-compose; SQLite is single-node only.
- **SQLite**
  File-based, zero-config, no JSONB
  - impact: PostgreSQL will be added to docker-compose; SQLite is single-node only.

**Agent Recommendation:** PostgreSQL

Reply with the option label to continue the pipeline.
```

### 2.4 处理时序

```
+--------------------+        +--------------------+       +--------+
| sub-agent.execute()|        | HumanDecisionManager|       |  user  |
+--------------------+        +--------------------+       +--------+
        |                              |                    |
        | create_decision_request()    |                    |
        |----------------------------->|                    |
        |     return HumanDecisionReq  |                    |
        |<-----------------------------|                    |
        |                              |                    |
        | build AgentOutput(human_decision=payload)         |
        |                              |                    |
        | v                            |                    |
        | 编排器 yield human_decision_required 事件          |
        |                              |                    |
        |                              |   show decision UI|
        |                              |------------------->|
        |                              |                    |
        |                              |  POST /decisions   |
        |                              |<-------------------|
        | resolve_decision(decision_id, answer)              |
        |<-----------------------------|                    |
        |                              |                    |
        | 编排器从断点继续执行                            |
        | emit 后续 stage_* 事件                          |
```

### 2.5 超时兜底

如果用户**没有在 deadline 前回答**：

1. `check_timeouts()` 把请求标记为 `TIMEOUT`
2. `apply_timeout_fallback(decision_id)` 自动采用 `recommended_option`
3. 流水线以推荐选项继续

这避免了"决策被遗忘导致流水线卡死"的问题。

### 2.6 升级路径

* Type-2 预算耗尽 → 调用 `request_human_decision` 升级为 Type-1
  （见 §3.4）
* 错误分类器 `ErrorKind.HUMAN_DECISION_TIMEOUT` → `RecoveryAction.TIMEOUT_FALLBACK`
  （见 [`WORKFLOW_GUIDE.md` 第 7 章](./WORKFLOW_GUIDE.md#7-异常处理与错误恢复机制)）

---

## 3. Type-2：非决策性对话延续

### 3.1 触发判定

子 agent 在任一阶段遇到下面任意一条**应当**开启 Type-2 对话：

1. **澄清** - "你说的 '高可用' 是 99.9% 还是 99.99%？"
2. **追加上下文** - "需要添加旧系统的迁移策略吗？"
3. **确认思路** - "我打算用 PostgreSQL 15 + pgbouncer，是否 OK？"
4. **部分产物预览** - "我已经生成了 3 个端点的契约，先看看？"
5. **任务未完成** - "我缺少 OAuth scope 列表"

反例（**不应该**用 Type-2）：

* 关键不可逆选择（应该用 Type-1）
* 答案显而易见的小问题（直接推进，不要打断）
* 用户在上一轮已经回答过的同样问题

### 3.2 状态机

```
start_conversation()                  request_continuation()
        |                                       |
        v                                       v
  task_status = in_progress              count += 1
        |                                       |
        v                                       v
  append_message(role, content)         if count < max:
        |                                       |  append question
        v                                       |  return (True, state)
  emit conversation_continuation event   else:
                                              |  return (False, state)
                                              |  -> 升级 Type-1
                                              v
                                       task_status = blocked
                                       escalated_decision_id set
```

### 3.3 触发原因分类（ConversationTrigger）

| Trigger                  | 含义                                       |
|--------------------------|--------------------------------------------|
| `clarification`          | 需要用户澄清已有信息                        |
| `additional_context`     | 需要用户补充新信息                          |
| `confirm_approach`       | 让用户确认当前方案                          |
| `incomplete_task`        | 任务没完成，需要更多信息                    |
| `partial_output_review`  | 部分产物先发用户预览                        |
| `other`                  | 兜底分类                                   |

UI 端可以根据 `trigger` 选择气泡样式（问答/确认/补全）。

### 3.4 自动升级

```python
conv_mgr = ConversationStateManager(max_continuations=3)
conv_id = conv_mgr.start_conversation(...)

# 子 agent 想再问一个问题
allowed, state = conv_mgr.request_continuation(conv_id, reason="need more auth details")
if not allowed:
    # 已经问了 max_continuations 次，升级为决策请求
    decision = decision_mgr.create_decision_request(
        stage=state.stage,
        question="您希望采用哪个 auth 方案？",
        ...
    )
    conv_mgr.mark_escalated(conv_id, decision.id)
    return AgentOutput(human_decision=decision.payload, ...)
```

### 3.5 处理时序

```
+------------------+      +----------------------+       +--------+
| sub-agent.execute|      | ConversationStateMgr |       |  user  |
+------------------+      +----------------------+       +--------+
      |                          |                       |
      | start_conversation()     |                       |
      |------------------------->|                       |
      |  return conv_id         |                       |
      |<-------------------------|                       |
      |                          |                       |
      |  ask_question() -> AgentOutput(                 |
      |      conversation_continuation=...)              |
      |  编排器 yield conversation_continuation 事件      |
      |                          |                       |
      |                          |  show chat bubble     |
      |                          |---------------------->|
      |                          |                       |
      |                          |  POST /messages       |
      |                          |<----------------------|
      |                          |  append_message       |
      |                          |  (count < max ?)      |
      |                          |  - yes -> ask more    |
      |                          |  - no  -> escalate    |
      |                          |                       |
      |  request_human_decision |                       |
      |  (因为 escalate)         |                       |
      |<-------------------------|                       |
      |                          |                       |
      |  流水线暂停, 等待用户决策   |                       |
```

### 3.6 与 Type-1 的对比

| 维度           | Type-1 决策                | Type-2 对话                 |
|----------------|----------------------------|-----------------------------|
| 流水线         | 暂停                       | 继续                        |
| 用户响应       | 选一个 label                | 自由文本                    |
| 数量上限       | 每次独立                    | `max_continuations`         |
| 升级条件       | 无                         | 计数耗尽 → 自动 Type-1      |
| 状态机         | pending → answered/timeout  | in_progress → completed/blocked |
| 模块           | `common/human_decision.py` | `common/conversation_state.py` |
| API            | `POST /decisions`           | `POST /conversations/{cid}/messages` |

---

## 4. API 形态

### 4.1 Type-1 决策

```http
# 列出某流水线所有待决决策
GET /api/devflow/run/{project_id}/decisions/pending
Response: [
  {
    "id": "dec-a1b2c3d4",
    "stage": "architecture",
    "question": "Which database should we use?",
    "background": "...",
    "options": [...],
    "recommended_option": "PostgreSQL",
    "deadline": "2026-06-03T12:00:00",
    "impact": "...",
    "related_artifacts": ["ARCHITECTURE.md"],
    "status": "pending",
    "message": "<rendered markdown>"
  }
]

# 提交答案
POST /api/devflow/run/{project_id}/decisions
{
  "decision_id": "dec-a1b2c3d4",
  "answer": "PostgreSQL"
}
Response: text/event-stream (resume pipeline)
```

### 4.2 Type-2 对话

```http
# 用户发消息
POST /api/devflow/run/{project_id}/conversations/{conversation_id}/messages
{
  "role": "user",
  "content": "use OAuth2 with PKCE"
}
Response: {
  "conversation_id": "conv-...",
  "task_status": "in_progress",
  "continuation_count": 1,
  "max_continuations": 3,
  ...
}
```

### 4.3 事件流

* `human_decision_required` - 子 agent 发出 Type-1
* `conversation_continuation` - 子 agent 发出 Type-2
* `pipeline_error` - 流水线失败（仅当 Type-2 升级也失败时）
