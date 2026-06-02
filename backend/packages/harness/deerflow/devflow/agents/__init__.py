"""DevFlow Sub-Agents - lazy registry.

Sub-agents are loaded on demand to avoid a circular import between
``agents/__init__.py`` and ``main_agent/orchestrator.py``.

To register a new agent:

1. Create ``agents/<name>/agent.py`` exposing a ``BaseSubAgent`` subclass.
2. Optionally add ``agents/<name>/config.md`` for the agent's skill scope.
3. Add ``<name>.md`` skill files to ``agents/<name>/skills/``.
4. Add the class to ``_build_registry()`` below.

Currently registered (in pipeline order):

* ``requirements``          - PRD + architecture (combined)
* ``frontend_design``       - frontend design package
* ``spec_development``      - formal API / data-model / state-machine specs
* ``code_testing``          - tests + coverage
* ``deployment``            - Docker/K8s manifests + deployment validation
"""
from __future__ import annotations

from typing import Type

from deerflow.devflow.agents.base import BaseSubAgent


def _build_registry() -> dict[str, Type[BaseSubAgent]]:
    from deerflow.devflow.agents.code_testing.agent import CodeTestingAgent
    from deerflow.devflow.agents.deployment.agent import DeploymentAgent
    from deerflow.devflow.agents.frontend_design.agent import FrontendDesignAgent
    from deerflow.devflow.agents.requirements.agent import RequirementsAgent
    from deerflow.devflow.agents.spec_development.agent import SpecDevelopmentAgent

    return {
        RequirementsAgent.name: RequirementsAgent,
        FrontendDesignAgent.name: FrontendDesignAgent,
        SpecDevelopmentAgent.name: SpecDevelopmentAgent,
        CodeTestingAgent.name: CodeTestingAgent,
        DeploymentAgent.name: DeploymentAgent,
    }


def get_agent_class(stage_or_name: str) -> Type[BaseSubAgent] | None:
    return _build_registry().get(stage_or_name)


def get_agent_registry() -> dict[str, Type[BaseSubAgent]]:
    """Return the current agent registry (snapshot)."""
    return _build_registry()


__all__ = [
    "BaseSubAgent",
    "get_agent_class",
    "get_agent_registry",
]
