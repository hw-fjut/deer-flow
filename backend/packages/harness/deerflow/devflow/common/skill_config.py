"""DevFlow skill configuration system.

A *skill* is a reusable behavior block defined in a single ``.md`` file with
YAML frontmatter. Skills are organised per-agent in
``agents/<agent_name>/skills/*.md``.

A user customises a sub-agent by editing only the ``.md`` files in that
agent's ``skills/`` directory - no Python change is required.

The loader supports:

* simple ``name: x`` / ``description: y`` / ``tools: [a, b]`` frontmatter
* list / scalar / boolean parsing
* loading a single skill, all skills for an agent, or a global registry
* hot-reloading via ``reload_all()``
* the special ``config.md`` file inside an agent folder, which describes the
  agent's overall skill scope, allowed tools, and history-access policy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("skill_config")

# Repo layout: backend/packages/harness/deerflow/devflow/{agents, common, ...}
DEFAULT_DEVFLOW_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class SkillDefinition:
    """Skill definition loaded from a ``.md`` file."""

    name: str
    content: str
    description: str = ""
    tools: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    output_format: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    file_path: Path | None = None


@dataclass
class AgentSkillScope:
    """Per-agent scope describing which skills it may use and how."""

    agent_name: str
    skills: list[SkillDefinition] = field(default_factory=list)
    description: str = ""
    history_access: str = "full"  # "full" | "frontend_design_only" | "isolated"
    allowed_stages: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def skill_names(self) -> list[str]:
        return [s.name for s in self.skills]


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _coerce_scalar(value: str) -> Any:
    """Best-effort YAML scalar coercion for our limited frontmatter subset."""
    value = value.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a tiny YAML subset used by DevFlow skill files."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    block = match.group(1)
    body = text[match.end():]
    metadata: dict[str, Any] = {}
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            metadata[key] = [_coerce_scalar(v) for v in items]
        else:
            metadata[key] = _coerce_scalar(value)
    return metadata, body


class SkillConfigLoader:
    """Load skill and agent scope definitions from ``.md`` files."""

    def __init__(self, devflow_root: Path | None = None, skills_dir: Path | None = None):
        self.devflow_root = devflow_root or DEFAULT_DEVFLOW_ROOT
        # Default: <devflow_root>/agents
        self.agents_dir = self.devflow_root / "agents"
        # Allow callers to override the per-agent skills directory in tests.
        self._skills_dir_override = skills_dir
        self._skill_cache: dict[str, SkillDefinition] = {}
        self._agent_scope_cache: dict[str, AgentSkillScope] = {}

    # --------------------------------------------------------- path resolution
    def skills_dir_for(self, agent_name: str) -> Path:
        if self._skills_dir_override is not None:
            return self._skills_dir_override / agent_name
        return self.agents_dir / agent_name / "skills"

    def config_file_for(self, agent_name: str) -> Path:
        return self.agents_dir / agent_name / "config.md"

    # -------------------------------------------------------------- single skill
    def load_skill(self, agent_name: str, skill_name: str) -> SkillDefinition | None:
        cache_key = f"{agent_name}/{skill_name}"
        if cache_key in self._skill_cache:
            return self._skill_cache[cache_key]

        skill_file = self.skills_dir_for(agent_name) / f"{skill_name}.md"
        if not skill_file.exists():
            logger.warning("Skill file not found: %s", skill_file)
            return None

        content = skill_file.read_text(encoding="utf-8")
        metadata, _body = _parse_frontmatter(content)
        skill = SkillDefinition(
            name=skill_name,
            content=content,
            description=str(metadata.get("description", "")),
            tools=list(metadata.get("tools", []) or []),
            constraints=list(metadata.get("constraints", []) or []),
            output_format=str(metadata.get("output_format", "")),
            raw_metadata=metadata,
            file_path=skill_file,
        )
        self._skill_cache[cache_key] = skill
        return skill

    # ----------------------------------------------------------------- agent
    def load_agent_scope(self, agent_name: str) -> AgentSkillScope:
        if agent_name in self._agent_scope_cache:
            return self._agent_scope_cache[agent_name]

        skills: list[SkillDefinition] = []
        skills_dir = self.skills_dir_for(agent_name)
        if skills_dir.exists():
            for skill_file in sorted(skills_dir.glob("*.md")):
                if skill_file.stem.startswith("_"):
                    continue
                skill = self.load_skill(agent_name, skill_file.stem)
                if skill:
                    skills.append(skill)

        description = ""
        history_access = "full"
        allowed_stages: list[str] = []
        extras: dict[str, Any] = {}

        config_file = self.config_file_for(agent_name)
        if config_file.exists():
            config_text = config_file.read_text(encoding="utf-8")
            config_meta, _ = _parse_frontmatter(config_text)
            description = str(config_meta.get("description", ""))
            history_access = str(config_meta.get("history_access", "full"))
            allowed_raw = config_meta.get("allowed_stages", [])
            if isinstance(allowed_raw, list):
                allowed_stages = [str(s) for s in allowed_raw]
            extras = {k: v for k, v in config_meta.items() if k not in {"description", "history_access", "allowed_stages"}}

        scope = AgentSkillScope(
            agent_name=agent_name,
            skills=skills,
            description=description,
            history_access=history_access,
            allowed_stages=allowed_stages,
            extras=extras,
        )
        self._agent_scope_cache[agent_name] = scope
        return scope

    # --------------------------------------------------------------- discovery
    def list_agents(self) -> list[str]:
        if not self.agents_dir.exists():
            return []
        return sorted(
            p.name
            for p in self.agents_dir.iterdir()
            if p.is_dir() and not p.name.startswith(("_", "."))
        )

    def list_skills(self, agent_name: str) -> list[str]:
        skills_dir = self.skills_dir_for(agent_name)
        if not skills_dir.exists():
            return []
        return sorted(p.stem for p in skills_dir.glob("*.md") if not p.stem.startswith("_"))

    def list_all_skills(self) -> dict[str, list[str]]:
        return {agent: self.list_skills(agent) for agent in self.list_agents()}

    # --------------------------------------------------------------- mutation
    def reload_all(self) -> None:
        self._skill_cache.clear()
        self._agent_scope_cache.clear()

    def reload_agent(self, agent_name: str) -> AgentSkillScope:
        self._agent_scope_cache.pop(agent_name, None)
        for cache_key in list(self._skill_cache.keys()):
            if cache_key.startswith(f"{agent_name}/"):
                self._skill_cache.pop(cache_key, None)
        return self.load_agent_scope(agent_name)


# --------------------------------------------------------- module-level singleton
_loader: SkillConfigLoader | None = None


def get_skill_loader(devflow_root: Path | None = None) -> SkillConfigLoader:
    """Return a process-wide skill loader."""
    global _loader
    if _loader is None:
        _loader = SkillConfigLoader(devflow_root=devflow_root)
    return _loader
