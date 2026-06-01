# DeerFlow Skill 召回与使用机制分析报告

> 最后更新: 2026-06-01
> 分析范围: Skill 定义、存储、加载、Prompt 注入、运行时使用全链路

---

## 目录

1. [概述](#1-概述)
2. [Skill 数据模型与文件规范](#2-skill-数据模型与文件规范)
3. [Skill 存储体系](#3-skill-存储体系)
4. [Skill 的加载与缓存机制](#4-skill-的加载与缓存机制)
5. [Skill 到 Prompt 的注入链路](#5-skill-到-prompt-的注入链路)
6. [运行时召回机制（渐进式加载模式）](#6-运行时召回机制渐进式加载模式)
7. [工具策略过滤](#7-工具策略过滤)
8. [Skill 管理（安装/编辑/删除/回滚）](#8-skill-管理安装编辑删除回滚)
9. [前后端 API 对接](#9-前后端-api-对接)
10. [关键文件索引](#10-关键文件索引)
11. [完整时序图](#11-完整时序图)

---

## 1. 概述

DeerFlow 的 Skill 系统是一套**可扩展的工作流定义框架**，允许通过 `SKILL.md` 文件定义特定任务的最佳实践、框架和资源引用。

Skill 的**召回机制核心思路**是 **Prompt 注入 + 按需加载（Progressive Loading）**：
- 不是将 Skill 内容预加载到 LLM 上下文中
- 而是在 System Prompt 中以 XML 标签告知 LLM 有哪些可用 Skill 及其文件位置
- LLM 在推理过程中通过 `read_file` 工具**按需主动读取** SKILL.md 内容
- 这种方式避免上下文膨胀，同时保持灵活性

---

## 2. Skill 数据模型与文件规范

### 2.1 目录结构规范

```
<skills_root>/
├── public/                          # 内置技能（不可编辑，只读）
│   ├── <skill-name>/
│   │   ├── SKILL.md                 # 技能主文件（唯一入口）
│   │   ├── references/              # 引用资料目录
│   │   ├── templates/               # 模板目录
│   │   ├── scripts/                 # 可执行脚本目录（安装时安全扫描）
│   │   └── assets/                  # 静态资源目录
│   └── ...
└── custom/                          # 用户自定义技能（可编辑）
    ├── <skill-name>/
    │   ├── SKILL.md
    │   └── ...
    └── .history/                    # 修改历史（JSONL格式）
        └── <skill-name>.jsonl
```

### 2.2 SKILL.md 文件格式

SKILL.md 使用 YAML frontmatter + Markdown 正文：

```markdown
---
name: my-skill                    # 必须，hyphen-case（小写字母、数字、连字符）
description: 技能功能描述          # 必须，最长1024字符，不能包含 <>
license: MIT                      # 可选
allowed-tools:                    # 可选，限制该技能可用的工具列表
  - read_file
  - write_file
  - bash
version: 1.0.0                    # 可选
author: someone                   # 可选（deprecated，建议用 metadata）
metadata:                         # 可选
  author: someone
  created: 2024-01-01
---

# ${skill name}

技能的具体工作流定义、最佳实践、框架说明...
```

### 2.3 Skill 数据模型

定义在 [skills/types.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/types.py)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | Skill 名称，hyphen-case |
| `description` | `str` | 简短功能描述 |
| `license` | `str \| None` | 许可证信息 |
| `skill_dir` | `Path` | Skill 目录路径 |
| `skill_file` | `Path` | SKILL.md 文件路径 |
| `relative_path` | `str` | 相对于 skills 根的路径 |
| `category` | `SkillCategory` | PUBLIC（内置）或 CUSTOM（自定义） |
| `allowed_tools` | `list[str]` | 允许使用的工具名称列表 |
| `enabled` | `bool` | 是否启用（默认为 True） |
| `get_container_file_path()` | 方法 | 返回容器内的完整文件路径 |

**SkillCategory 枚举**：
```python
class SkillCategory(str, Enum):
    PUBLIC = "public"   # 内置、只读
    CUSTOM = "custom"   # 用户自定义、可编辑
```

---

## 3. Skill 存储体系

### 3.1 抽象存储接口

[SkillStorage](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/storage/skill_storage.py) 是抽象基类，定义了完整的模板方法：

```
SkillStorage (ABC)
│
├── 静态协议方法（非存储特定）
│   ├── validate_skill_name()          # 校验技能名称格式
│   ├── validate_relative_path()       # 校验相对路径（防 path traversal）
│   ├── validate_skill_markdown_content()  # 校验 SKILL.md 内容
│   └── ensure_safe_support_path()     # 校验附属文件路径
│
├── 抽象原子操作（子类必须实现）
│   ├── get_skills_root_path()
│   ├── _iter_skill_files()            # 遍历所有 SKILL.md
│   ├── read_custom_skill()
│   ├── write_custom_skill()
│   ├── ainstall_skill_from_archive()  # 从 .skill ZIP 安装
│   ├── delete_custom_skill()
│   ├── custom_skill_exists()
│   ├── public_skill_exists()
│   ├── append_history()               # JSONL 格式
│   └── read_history()
│
├── 路径辅助方法
│   ├── get_container_root()
│   ├── get_custom_skill_dir()
│   ├── get_custom_skill_file()
│   └── get_skill_history_file()
│
└── 模板方法（final）
    └── load_skills(enabled_only=False)  # 发现 + 解析 + 合并启用状态 + 排序
```

### 3.2 文件系统实现

[LocalSkillStorage](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/storage/local_skill_storage.py) 实现了所有抽象方法：

- **遍历**：`os.walk()` 递归扫描 `public/` 和 `custom/` 目录
- **写入**：使用 `tempfile.NamedTemporaryFile` 原子写入（先写临时文件再 rename）
- **安装**：解压 `.skill` ZIP → 验证 frontmatter → 安全扫描 → staging 目录 → atomic move
- **删除**：`shutil.rmtree()`，同时记录历史
- **历史**：JSONL 格式追加写入 `.history/<name>.jsonl`

### 3.3 存储工厂函数

```python
from deerflow.skills.storage import get_or_new_skill_storage

# 全局单例延迟初始化
storage = get_or_new_skill_storage(app_config=config)
```

---

## 4. Skill 的加载与缓存机制

### 4.1 load_skills 模板方法

[skill_storage.py#L212-L246](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/storage/skill_storage.py#L212-L246)

```
load_skills(enabled_only=False)
   │
   ├── _iter_skill_files()           ← 遍历 skills/{public,custom}/**/SKILL.md
   │       │
   │       └── parse_skill_file()    ← 解析 YAML frontmatter → Skill 对象
   │              │
   │              ├── yaml.safe_load(frontmatter)
   │              ├── 提取 name, description, license, allowed-tools
   │              └── parse_allowed_tools() ← 支持 "*"（全部允许）、列表、折叠块
   │
   ├── 合并所有 skill，按 name 去重（custom 覆盖 public）
   │
   ├── 读取 extensions_config.json    ← 获取每个 skill 的启用状态
   │       │
   │       └── ExtensionsConfig.from_file()
   │               └── is_skill_enabled(name, category)
   │
   ├── 若 enabled_only=True → 过滤掉 disabled 的 skill
   │
   └── 按 name 排序后返回 list[Skill]
```

### 4.2 双层 Prompt 缓存体系

[prompt.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py) 实现了两层缓存：

```
第一层：Skill 对象缓存
─────────────────────
_enabled_skills_cache: list[Skill] | None    ← 全局单例，后台线程异步刷新
_enabled_skills_by_config_cache:             ← 按 AppConfig 对象身份缓存
    dict[int, tuple[object, list[Skill]]]       （请求级注入的 config 专用）

  缓存失效时：
    _enabled_skills_cache = None
    _enabled_skills_by_config_cache.clear()
    版本号 += 1
    启动后台刷新线程（daemon）

  后台线程 _refresh_enabled_skills_cache_worker():
    while True:
        读取当前版本号
        调用 _load_enabled_skills_sync()  ← 磁盘 I/O
        检查版本号是否匹配
           匹配 → 写入缓存，结束
           不匹配 → 重新加载（保证收敛到最新版本）


第二层：Prompt 文本缓存
─────────────────────
_get_cached_skills_prompt_section()           ← @lru_cache(maxsize=32)
  缓存键: (skill_signature, available_key, container_base_path, skill_evolution_section)
  其中 skill_signature 为 (name, description, category, location) 元组

  当 skill 安装/编辑/删除时自动清除
```

### 4.3 缓存刷新流程

```
任何 Skill 变更（安装/编辑/开关/删除）
   │
   └── refresh_skills_system_prompt_cache_async()
           │
           ├── _invalidate_enabled_skills_cache()
           │       │
           │       ├── _get_cached_skills_prompt_section.cache_clear()  ← 清除 lru_cache
           │       ├── _enabled_skills_cache = None
           │       ├── _enabled_skills_by_config_cache.clear()
           │       ├── _enabled_skills_refresh_version += 1
           │       └── 启动后台刷新线程
           │
           └── await asyncio.to_thread(event.wait())   ← 等待后台加载完成（最长5秒）
```

---

## 5. Skill 到 Prompt 的注入链路

### 5.1 调用链

```
apply_prompt_template()
       │
       ├── get_skills_prompt_section()
       │       │
       │       ├── get_enabled_skills_for_config(app_config)
       │       │       │
       │       │       ├── 检查 _enabled_skills_by_config_cache
       │       │       ├── 未命中 → load_skills(enabled_only=True)
       │       │       └── 返回 list[Skill]（仅含已启用的）
       │       │
       │       ├── 构建 skill_signature 元组
       │       │   (name, description, category, container_file_path)
       │       │
       │       └── _get_cached_skills_prompt_section(...)
       │               │
       │               └── 生成 <skill_system> XML 块
       │
       ├── get_agent_soul()             ← Agent 角色定义
       ├── get_memory_section()         ← 记忆信息
       ├── get_tools_prompt_section()   ← 工具说明
       └── ...其他 prompt 片段
```

### 5.2 生成的 Prompt 片段

```xml
<skill_system>
You have access to skills that provide optimized workflows for specific tasks.
Each skill contains best practices, frameworks, and references to additional
resources.

**Progressive Loading Pattern:**
1. When a user query matches a skill's use case, immediately call `read_file` on
   the skill's main file using the path attribute provided in the skill tag below
2. Read and understand the skill's workflow and instructions
3. The skill file contains references to external resources under the same folder
4. Load referenced resources only when needed during execution
5. Follow the skill's instructions precisely

**Skills are located at:** /mnt/skills

<available_skills>
    <skill>
        <name>my-skill</name>
        <description>Does X. [built-in]</description>
        <location>/mnt/skills/public/my-skill/SKILL.md</location>
    </skill>
    <skill>
        <name>user-skill</name>
        <description>Does Y. [custom, editable]</description>
        <location>/mnt/skills/custom/user-skill/SKILL.md</location>
    </skill>
</available_skills>

</skill_system>
```

#### 5.2.1 技能类型标签

- **`[built-in]`**：内置技能，标记为只读
- **`[custom, editable]`**：自定义技能，标记为可编辑

#### 5.2.2 Skill Self-Evolution 模式

当 `config.skill_evolution.enabled=True` 时，额外插入：

```
## Skill Self-Evolution
After completing a task, consider creating or updating a skill when:
- The task required 5+ tool calls to resolve
- You overcame non-obvious errors or pitfalls
- The user corrected your approach and the corrected version worked
- You discovered a non-trivial, recurring workflow
If you used a skill and encountered issues not covered by it, patch it immediately.
Prefer patch over edit. Before creating a new skill, confirm with the user first.
Skip simple one-off tasks.
```

---

## 6. 运行时召回机制（渐进式加载模式）

### 6.1 核心召回流程

```
用户输入 "实现一个 REST API 用户认证模块"
   │
   ▼
LLM 接收 System Prompt（含 <skill_system> 片段）
   │
   ▼
LLM 理解用户请求，匹配到 "rest-api" skill 的 use case
   │
   ▼
LLM 调用 read_file 工具：
  read_file(path="/mnt/skills/public/rest-api/SKILL.md")
   │
   ▼
LLM 读取 SKILL.md 内容，理解工作流：
  - 项目结构最佳实践
  - 推荐的库和框架
  - 认证流程模板
   │
   ▼
LLM 按需加载 references/ 下的资源：
  read_file(path="/mnt/skills/public/rest-api/references/auth-flow.md")
   │
   ▼
LLM 按照 skill 指导执行任务
```

### 6.2 设计优势

| 对比项 | 预加载模式 | DeerFlow 渐进式加载 |
|--------|-----------|-------------------|
| 上下文占用 | 所有 skill 内容都占用 token | 仅 skill 列表描述占用极少 token |
| 启动延迟 | 无额外延迟 | 首次 `read_file` 有轻微 I/O 延迟 |
| 灵活性 | 上下文窗口固定，有限制 | 可加载任意数量的附属资源 |
| 资源利用 | 不相关的 skill 也占用 token | 按需加载，不浪费 token |

---

## 7. 工具策略过滤

### 7.1 工具过滤机制

[tool_policy.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/tool_policy.py) 实现了 Skill 级别的工具访问控制：

```python
def allowed_tool_names_for_skills(skills: Iterable[Skill]) -> set[str]:
    """取所有启用的 skill 中 allowed_tools 的并集"""
    result: set[str] = set()
    for skill in skills:
        if skill.allowed_tools:
            result.update(skill.allowed_tools)
    return result

def filter_tools_by_skill_allowed_tools(graph, skills):
    """根据 skill.allowed_tools 过滤 Agent 的可用工具"""
```

### 7.2 工作方式

- 若 skill 未声明 `allowed-tools`：不产生任何限制
- 若 skill 声明了 `allowed-tools: [read_file, write_file]`：
  - 当该 skill 启用时，Agent 的工具集被限制为仅 read_file 和 write_file
  - 多个 skill 的 allowed_tools 取**并集**
- 过滤发生在 Lead Agent 创建时，作为中间件链的一部分

---

## 8. Skill 管理（安装/编辑/删除/回滚）

### 8.1 HTTP API 接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/skills` | GET | 获取所有技能列表 |
| `/api/skills/{name}` | GET | 获取单个技能详情 |
| `/api/skills/{name}` | PUT | 启用/禁用技能 |
| `/api/skills/install` | POST | 从 .skill ZIP 安装技能 |
| `/api/skills/custom` | GET | 列出自定义技能 |
| `/api/skills/custom/{name}` | GET | 获取自定义技能内容 |
| `/api/skills/custom/{name}` | PUT | 编辑自定义技能 |
| `/api/skills/custom/{name}` | DELETE | 删除自定义技能 |
| `/api/skills/custom/{name}/history` | GET | 获取修改历史 |
| `/api/skills/custom/{name}/rollback` | POST | 回滚到历史版本 |

### 8.2 LLM 工具接口

[skill_manage_tool](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/tools/skill_manage_tool.py) 是一个 LangChain `@tool`，LLM 可通过对话直接管理技能：

| 动作 | 描述 |
|------|------|
| `create` | 创建新 custom skill |
| `edit` | 替换整个 SKILL.md |
| `patch` | 部分替换（`find`/`replace`） |
| `delete` | 删除 custom skill |
| `write_file` | 写入附属文件 |
| `remove_file` | 删除附属文件 |

**安全特性**：
- 所有写入操作前调用 `scan_skill_content()` 安全扫描
- 并发控制：按 skill name 使用 `asyncio.Lock`
- 路径验证：`validate_skill_markdown_content()` + `ensure_safe_support_path()`

### 8.3 安装流程（.skill ZIP）

```
POST /api/skills/install { thread_id, path }
   │
   ├── 1. resolve_thread_virtual_path()      解析线程中的 .skill 文件路径
   │
   ├── 2. 打开 ZIP 文件
   │       ├── zipfile.ZipFile(path, "r")
   │       └── safe_extract_skill_archive()   安全解压
   │
   ├── 3. resolve_skill_dir_from_archive()    在解压目录中定位 SKILL.md
   │
   ├── 4. _validate_skill_frontmatter()       校验 frontmatter
   │       ├── 必须包含 name 和 description
   │       ├── name 必须为 hyphen-case
   │       └── 不能包含不允许的属性
   │
   ├── 5. 检查是否已存在同名 skill
   │       └── 存在 → SkillAlreadyExistsError (409)
   │
   ├── 6. _scan_skill_archive_contents_or_raise()  安全扫描
   │       └── 扫描所有文件，检查恶意内容
   │
   ├── 7. 安装到 skills/custom/<name>/
   │       ├── 先解压到 staging 目录（前缀 .installing-）
   │       └── atomic rename 到目标目录
   │
   └── 8. refresh_skills_system_prompt_cache_async()  刷新缓存
```

### 8.4 启用/禁用流程

```
PUT /api/skills/{skill_name} { enabled: true/false }
   │
   ├── 1. 读取 extensions_config.json
   │
   ├── 2. 更新 skills[name].enabled = request.enabled
   │
   ├── 3. 写回 extensions_config.json
   │
   ├── 4. reload_extensions_config()  重载配置
   │
   └── 5. refresh_skills_system_prompt_cache_async()  刷新缓存
```

---

## 9. 前后端 API 对接

### 9.1 前端 API 客户端

[frontend/src/core/skills/api.ts](file:///home/hw/sourceCode/deer-flow/frontend/src/core/skills/api.ts)：

```typescript
export async function loadSkills(): Promise<Skill[]>       // GET /api/skills
export async function enableSkill(                         // PUT /api/skills/{name}
  skillName: string, enabled: boolean
): Promise<Skill>
export async function installSkill(                        // POST /api/skills/install
  threadId: string, path: string
): Promise<{ success: boolean; skill_name: string; message: string }>
```

### 9.2 Mock API

[frontend/src/app/mock/api/skills/route.ts](file:///home/hw/sourceCode/deer-flow/frontend/src/app/mock/api/skills/route.ts)：

```typescript
// 返回示例数据，包含 public 和 custom 两种类型
const mockSkills = [
  {
    name: "example-skill",
    description: "An example skill",
    license: "MIT",
    category: "public",
    enabled: true,
  },
  // ...
];
```

---

## 10. 关键文件索引

### 后端核心文件

| 文件路径 | 角色 | 关键功能 |
|---------|------|---------|
| [backend/.../skills/types.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/types.py) | **数据模型** | `Skill` 类、`SkillCategory` 枚举、`SKILL_MD_FILE` 常量 |
| [backend/.../skills/parser.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/parser.py) | **文件解析** | `parse_skill_file()`、`parse_allowed_tools()`、YAML frontmatter 提取 |
| [backend/.../skills/validation.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/validation.py) | **内容校验** | `_validate_skill_frontmatter()`、字段格式检查 |
| [backend/.../skills/installer.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/installer.py) | **安装器** | `.skill` ZIP 解压、安全扫描、原子安装 |
| [backend/.../skills/security_scanner.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/security_scanner.py) | **安全扫描** | 文件内容安全检测 |
| [backend/.../skills/tool_policy.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills·_tool_policy.py) | **工具过滤** | `allowed_tool_names_for_skills()`、`process_skills_tool_policy()` |
| [backend/.../skills/storage/skill_storage.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness│storage/skill_storage.py) | |deerrow>抽象基类 +load_skills()</s>erlow> 模板 * | `SkillStorage(ABC)` + `load_skills()` + 路径辅助 + validation helpers + 安装/历史 atomic ops |
| [backend/.../skills/storage/local_skill_storage.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/storage/local_skill_storage.py) | **文件系统实现** | `LocalSkillStorage` + `ainstall_skill_from_archive()` + `_iter_skill_files()` + atomic write + history JSONL |
| [backend/.../skills/storage/\_\_init\_\_.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/skills/storage/__init__.py) | **工厂入口** | `get_or_new_skill_storage()` 全局单例 |
| [backend/.../agents/lead_agent/prompt.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py) | **Prompt 注入与缓存** | `get_skills_prompt_section()`、`get_enabled_skills_for_config()`、`refresh_skills_system_prompt_cache_async()`、`get_cached_enabled_skills()` |
| [backend/.../tools/skill_manage_tool.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/tools/skill_manage_tool.py) | **运行时管理工具** | `skill_manage_tool` 的 create/edit/patch/delete/write_file/remove_file |
| [backend/.../config/skills_config.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/config/skills_config.py) | **技能配置** | `SkillsConfig`（目录路径、容器路径） |
| [backend/.../config/extensions_config.py](file:///home/hw/sourceCode/deer-flow/backend/packages/harness/deerflow/config/extensions_config.py) | **扩展配置** | `extensions_config.json` 管理、skill 启用/禁用状态 |

### 路由层

| 文件路径 | 角色 | 关键功能 |
|---------|------|---------|
| [backend/app/gateway/routers/skills.py](file:///home/hw/sourceCode/deer-flow/backend/app/gateway/routers/skills.py) | **HTTP 路由** | 13 个 Restful 端点（CRUD + 安装 + 开关 + 回滚） |
| [backend/app/gateway/path_utils.py](file:///home/hw/sourceCode/deer-flow/backend/app/gateway/utils.py) | **路径工具** | `resolve_thread_virtual_path()` 虚拟路径→真实路径 |

### 前端文件

| 文件路径 | 角色 | 关键功能 |
|---------|------|---------|
| [frontend/src/core/skills/api.ts](file:///home/hw/sourceCode/deer-flow/frontend/src/core/skills/api.ts) | **API 客户端** | `loadSkills()`、`enableSkill()`、`installSkill()` |

### Mock 文件

| 文件路径 | 角色 | 关键功能 |
|---------|------|---------|
| [frontend/src/app/mock/api/skills/route.ts](file:///home/hw/sourceCode/deer-flow/frontend/src/app/mock/api/skills/route.ts) | **Mock API** | 示例技能数据，支持列表和安装 |

---

## 11. 完整时序图

```
Agent 创建
   │
   ▼
apply_prompt_template()
   │
   ├── get_skills_prompt_section()
   │       │
   │       ├── get_enabled_skills_for_config()
   │       │       │
   │       │       ├── [缓存命中] → 返回缓存的 list[Skill]
   │       │       │
   │       │       └── [缓存未命中]
   │       │               │
   │       │               ├── get_or_new_skill_storage().load_skills(enabled_only=True)
   │       │               │       │
   │       │               │       ├── _iter_skill_files()  → 遍历目录
   │       │               │       ├── parse_skill_file()   → 解析 SKILL.md
   │       │               │       ├── extensions_config    → 合并启用状态
   │       │               │       ├── 过滤 enabled_only
   │       │               │       └── 排序 → list[Skill]
   │       │               │
   │       │               └── 缓存结果
   │       │
   │       ├── 构建 skill_signature  = (name, desc, cat, location)...
   │       │
   │       └── _get_cached_skills_prompt_section.signature)
   │               │
   │               ├── [lru_cache 命中] → 返回缓存的 XML 字符串
   │               │
   │               └── [lru_cache 未命中]
   │                       │
   │                       └── 生成 <skill_system> XML 块
   │
   └── 完整 system prompt = 基础规则 + skills_section + memory + tools + ...
   │
   ▼
LLM 接收 system prompt，开始推理
   │
   ▼
用户发送消息 → LLM 匹配 Skill use case
   │
   ▼
LLM 调用 read_file(<location>)  ← 按需加载！
   │
   ├── 读取 SKILL.md 内容
   │
   ├── 理解工作流和指令
   │
   ├── 按需加载附属资源（references/templates/scripts）
   │
   └── 精确遵循 skill 指导执行任务
   │
   ▼
[运行时] LLM 发现问题 → skill 需要更新
   │
   ▼
LLM 调用 skill_manage_tool("patch", name="my-skill", ...)
   │
   ├── 安全扫描内容
   │
   ├── 写入更新后的 SKILL.md
   │
   ├── 记录历史 (JSONL)
   │
   └── refresh_skills_system_prompt_cache_async()
           │
           ├── _get_cached_skills_prompt_section.cache_clear()
           ├── _enabled_skills_cache = None
           ├── 启动后台刷新线程
           └── 等待刷新完成
   │
   ▼
[用户端] 前端管理页面
   │
   ├── GET /api/skills → 列表展示
   │
   ├── PUT /api/skills/{name} {enabled: false} → 禁用
   │
   └── POST /api/skills/install → 上传 .skill 文件
```

---

## 总结

DeerFlow 的 Skill 召回机制具有以下特点：

1. **按需加载（Progressive Loading）**：不预加载 Skill 内容到上下文，通过 `read_file` 按需读取，节省 Token
2. **双层缓存**：Skill 对象缓存（后台线程异步刷新）+ Prompt 文本缓存（`@lru_cache`），兼顾性能与实时性
3. **安全可控**：安装时安全扫描、路径遍历防护、工具级别权限控制
4. **闭环管理**：LLM 可通过 `skill_manage_tool` 在运行时创建/编辑/删除 Skill，形成"使用→发现问题→改进"的自演化闭环
5. **前后端分离**：完整 HTTP API + 前端客户端，支持 Web 界面管理