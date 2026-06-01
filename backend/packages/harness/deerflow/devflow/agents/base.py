"""Base agent definition"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from deerflow.devflow.common.logging import setup_logger


@dataclass
class AgentInput:
    """Agent input"""
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    previous_artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    """Agent output"""
    result: str
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None
    completed_at: datetime = field(default_factory=datetime.now)


class BaseSubAgent(ABC):
    """Base class for sub-agents"""
    
    name: str = ""
    description: str = ""
    stage: str = ""
    
    def __init__(self):
        self.logger = setup_logger(f"agent.{self.name}")
    
    @abstractmethod
    async def execute(self, input: AgentInput) -> AgentOutput:
        """Execute agent task
        
        Args:
            input: Agent input
            
        Returns:
            AgentOutput: Agent output
        """
        pass
    
    @abstractmethod
    def get_system_prompt(self, context: dict[str, Any]) -> str:
        """Get system prompt
        
        Args:
            context: Project context
            
        Returns:
            System prompt string
        """
        pass
    
    def validate_input(self, input: AgentInput) -> None:
        """Validate input
        
        Args:
            input: Agent input
            
        Raises:
            ValueError: If input is invalid
        """
        if not input.task:
            raise ValueError("Task cannot be empty")
    
    def format_context(self, context: dict[str, Any]) -> str:
        """Format context as text
        
        Args:
            context: Project context
            
        Returns:
            Formatted context text
        """
        lines = ["## Project Context", ""]
        
        if "name" in context:
            lines.append(f"Project Name: {context['name']}")
        if "description" in context:
            lines.append(f"Description: {context['description']}")
        
        artifacts = context.get("artifacts", {})
        if artifacts:
            lines.append("")
            lines.append("## Previous Artifacts")
            lines.append("")
            for stage, artifact in artifacts.items():
                lines.append(f"### {stage}")
                lines.append(f"Name: {artifact.get('name', 'N/A')}")
                lines.append(f"Content: {artifact.get('content', 'N/A')[:500]}...")
                lines.append("")
        
        return "\n".join(lines)
