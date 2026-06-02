# DevFlow 技能 .md 配置编写指南

> 本文件说明如何**只通过修改 Markdown 文件**完成对子 agent 的定制。
> 不需要改动任何 Python 代码。

---

## 1. 文件位置

DevFlow 启动时扫描以下两个位置：

| 路径                                  | 用途                                       |
|---------------------------------------|--------------------------------------------|
| `agents/<name>/config.md`             | 定义该 agent 的**整体**范围                 |
| `agents/<name>/skills/<skill>.md`     | 定义该 agent 的**单个**技能（可多个）       |

示例：

```
backend/packages/harness/deerflow/devflow/agents/
├── frontend_design/
│   ├── config.md
│   └── skills/
│       ├── design_tokens.md
│       ├── page_blueprints.md
│       ├── component_inventory.md
│       ├── routing_and_state.md
│       └── api_contract_summary.md
├── spec_development/
│   ├── config.md
│   └── skills/
│       ├── spec_api_design.md
│       └── spec_data_model.md
└── ...
```

---

## 2. Frontmatter 字段说明

DevFlow 用的是 YAML 的一个**最小子集**，仅支持以下结构：

```yaml
---
name: <string>            # 文件名 / 技能名（可选，与文件名一致即可）
description: <string>     # 必填：给编排器和 LLM 看的简短描述
tools: [tool1, tool2]     # 选填：声明该 agent/skill 可调用的工具
constraints: [rule1, rule2] # 选填：硬约束（注入到 system prompt）
output_format: markdown   # 选填：默认 markdown
history_access: <policy>  # 仅 config.md：full / frontend_design_only /
                          #             frontend_design_and_spec /
                          #             frontend_design_and_testing
allowed_stages: [stage1]  # 仅 config.md：声明此 agent 能跑的阶段
---
```

### 2.1 字段约束

* `name`：可省略，省略时取文件名（去掉 `.md`）
* `description`：必填，agent system prompt 会引用它
* `tools`：`[name1, name2]` 形式；当前未对工具做强制解析（保留给未来）
* `constraints`：`[rule1, rule2]` 形式；`rule` 是一句话规则
* `output_format`：当前仅作记录用，未来用于 JSON 输出校验
* `history_access`：仅 `config.md` 使用，决定 agent 看到哪些上游产物
* `allowed_stages`：仅 `config.md` 使用；保留字段，编排器当前未强制检查

### 2.2 不支持的语法

* 嵌套 map（如 `tools: {read: [a, b]}`）
* 引用 & 锚点
* 多文档（`---`）
* 数字、布尔（仅在解析失败时保留为字符串）

---

## 3. 完整示例

### 3.1 `config.md`

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

The Frontend Design Agent is the bridge between the system architecture and
the iterative spec/test/deploy loop.

## When this agent runs
- After ``architecture`` completes
- Before the loop subgraph (spec_development -> code_testing -> deployment) starts

## Inputs
- ``architecture`` artifact (full text)
- Project name and description

## Outputs
- ``design_tokens.md``
- ``page_blueprints.md``
- ``component_inventory.md``
- ``routing_and_state.md``
- ``api_contract_summary.md``

## History access policy
Full access. The agent is the *last* stage that is allowed to look at the
requirements / architecture context freely.
```

### 3.2 `skills/<skill>.md`

`agents/frontend_design/skills/design_tokens.md`：

```markdown
---
name: design_tokens
description: Define the visual design tokens (colors, typography, spacing, motion) that the rest of the frontend consumes.
tools: [file_write, file_read, markdown_parse]
constraints: [no_inline_hex_outside_tokens, follow_design_system_naming, use_4px_base_grid]
output_format: markdown
---

# Design Tokens Skill

## Overview
The Frontend Design Agent uses this skill to emit a single source-of-truth
``design_tokens.md`` describing the visual language of the project.

## Capabilities
- Define a color palette (brand + neutral + semantic) with WCAG AA contrast notes
- Define typography scale (font families, sizes, weights, line heights)
- Define spacing, radius, and elevation scales
- Define motion (duration curves, allowed easing tokens)
- Map every primitive to a CSS variable / Tailwind token name

## Usage Guidelines
1. Tokens must be the only place where raw hex / px values appear
2. The output must be importable by the chosen UI framework
3. Mark deprecated tokens explicitly so the spec/test loop can detect drift
```

---

## 4. 加载与生效

### 4.1 启动时

`SkillConfigLoader.__init__()` 默认在 `devflow_root/agents/` 下扫描。

```python
from deerflow.devflow.common.skill_config import get_skill_loader
loader = get_skill_loader()
print(loader.list_agents())
# ['architecture', 'code_testing', 'deployment', 'frontend_design', 'requirements', 'spec_development']
print(loader.list_skills('frontend_design'))
# ['api_contract_summary', 'component_inventory', 'design_tokens', 'page_blueprints', 'routing_and_state']
```

### 4.2 运行时热重载

修改 `.md` 后，无需重启进程，调用：

```http
POST /api/devflow/skills/reload
Response: {"reloaded": true, "agents": ["architecture", "code_testing", ...]}
```

或者在 Python 中：

```python
from deerflow.devflow.common.skill_config import get_skill_loader
get_skill_loader().reload_all()
```

### 4.3 Agent 内访问

`BaseSubAgent` 自动加载并暴露 skill：

```python
class MyAgent(BaseSubAgent):
    name = "my_agent"

    async def execute(self, input: AgentInput) -> AgentOutput:
        # 直接拿某个 skill 的元数据
        skill = self.get_skill("design_tokens")
        # skill.description / skill.tools / skill.constraints / skill.output_format

        # 拿到所有 skill 名
        names = self.list_skill_names()

        # 重新加载（重命名/新增后）
        self.reload_skills()

        ...
```

`get_system_prompt` 默认会渲染 `render_skill_prompt()`，把 skills
注入到 system prompt。

---

## 5. 常见定制场景

### 5.1 让某个 agent 临时禁用一个 skill

最简单：把对应 `.md` 文件**改名**，加 `_` 前缀就不会被加载：

```bash
mv agents/frontend_design/skills/routing_and_state.md \
   agents/frontend_design/skills/_routing_and_state.md
```

### 5.2 给一个 agent 加上"必须输出 OpenAPI 3.1"的约束

编辑 `agents/spec_development/config.md`，在 `constraints` 里追加：

```yaml
constraints: [version_path_prefixed, error_model_uniform, every_endpoint_listed, must_be_openapi_3_1]
```

约束会自动注入到 system prompt。

### 5.3 改变循环子图某个 agent 的可见输入

编辑 `agents/spec_development/config.md`：

```yaml
history_access: frontend_design_and_spec   # 改为这个会让 spec 同时看到上次 spec 产物
```

> 注意：当前编排器只为 spec_development 强制 `frontend_design_only`。
> 真正改编排器逻辑要修改 `LOOP_STAGE_ACCESS` 字典；config.md 中的
> 字段是"声明"，让 UI 与审计可见。

### 5.4 给 agent 增/换工具

直接在 `tools` 字段追加或替换：

```yaml
tools: [file_write, file_read, code_execute, web_search, image_search]
```

> 工具本身需要在 `BaseSubAgent` 或更上层执行器中实现。当前 `.md` 中的
> `tools` 是"声明"，让 LLM 知道它能用什么。

### 5.5 完全新增一个 agent

1. 创建 `agents/<new_agent>/config.md`
2. 创建 `agents/<new_agent>/skills/<skill>.md`（可多个）
3. 在 `deerflow/devflow/agents/__init__.py` 的 `_build_registry()` 中加一行：
   ```python
   return {
       ...
       "new_agent": NewAgentClass,
   }
   ```
4. （可选）在 `deerflow/devflow/main_agent/state.py` 的 `PipelineStage`
   中加新阶段

这是**唯一**需要改 Python 的场景，但改动非常小。

---

## 6. 调试技巧

### 6.1 看 agent 实际加载的 skills

```python
from deerflow.devflow.common.skill_config import get_skill_loader
scope = get_skill_loader().load_agent_scope("frontend_design")
print(scope.description)
print(scope.skill_names())
for s in scope.skills:
    print(s.name, "->", s.tools, s.constraints, s.output_format)
```

### 6.2 看 agent 收到的 system prompt

```python
agent = FrontendDesignAgent()
ctx = {
    "name": "demo",
    "description": "demo project",
    "artifacts": {"frontend_design": {"name": "...", "content": "..."}},
    "current_stage": "spec_development",
    "history_access_policy": "frontend_design_only",
}
print(agent.get_system_prompt(ctx))
```

### 6.3 用 API 查看

```http
GET /api/devflow/skills
GET /api/devflow/skills/frontend_design
```
