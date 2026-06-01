"""Memory system data models"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MemoryType(str, Enum):
    """Memory type enum"""
    REQUIREMENT = "requirement"
    ARCHITECTURE = "architecture"
    CODE = "code"
    TEST = "test"
    DEPLOYMENT = "deployment"
    CONTEXT = "context"
    DECISION = "decision"

@dataclass
class MemoryEntry:
    """Memory entry model"""
    project_id: str
    stage: str
    memory_type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class StageArtifact:
    """Stage artifact model"""
    project_id: str
    stage: str
    name: str
    content: str
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ProjectMemory:
    """Project memory model"""
    project_id: str
    name: str
    description: str
    current_stage: str = "requirements"
    artifacts: list[StageArtifact] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def get_artifact(self, stage: str) -> StageArtifact | None:
        """Get artifact for specified stage"""
        for artifact in self.artifacts:
            if artifact.stage == stage:
                return artifact
        return None
    
    def update_stage(self, stage: str) -> None:
        """Update current stage"""
        self.current_stage = stage
        self.updated_at = datetime.now()
