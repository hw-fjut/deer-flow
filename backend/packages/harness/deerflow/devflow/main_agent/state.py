"""Pipeline state definitions"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PipelineStage(str, Enum):
    """Pipeline stages"""
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEPLOYMENT = "deployment"


class PipelineStatus(str, Enum):
    """Pipeline status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class StageResult:
    """Stage execution result"""
    stage: PipelineStage
    success: bool
    output: str
    files: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration_seconds: float = 0.0


@dataclass
class PipelineState:
    """Pipeline state"""
    project_id: str
    name: str
    description: str
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: PipelineStage = PipelineStage.REQUIREMENTS
    completed_stages: list[StageResult] = field(default_factory=list)
    failed_stage: StageResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_stage_result(self, stage: PipelineStage) -> StageResult | None:
        """Get result for specified stage"""
        for result in self.completed_stages:
            if result.stage == stage:
                return result
        return None
    
    def mark_stage_completed(self, result: StageResult) -> None:
        """Mark stage as completed"""
        result.completed_at = datetime.now()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        self.completed_stages.append(result)
        
        # Advance to next stage
        stage_order = list(PipelineStage)
        current_idx = stage_order.index(self.current_stage)
        if current_idx < len(stage_order) - 1:
            self.current_stage = stage_order[current_idx + 1]
    
    def mark_failed(self, result: StageResult) -> None:
        """Mark pipeline as failed"""
        result.completed_at = datetime.now()
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        self.failed_stage = result
        self.status = PipelineStatus.FAILED
        self.completed_at = result.completed_at
    
    def mark_completed(self) -> None:
        """Mark pipeline as completed"""
        self.status = PipelineStatus.COMPLETED
        self.completed_at = datetime.now()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "current_stage": self.current_stage.value,
            "completed_stages": [
                {
                    "stage": r.stage.value,
                    "success": r.success,
                    "output": r.output,
                    "files": r.files,
                    "error": r.error,
                    "started_at": r.started_at.isoformat(),
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "duration_seconds": r.duration_seconds,
                }
                for r in self.completed_stages
            ],
            "failed_stage": {
                "stage": self.failed_stage.stage.value,
                "error": self.failed_stage.error,
            } if self.failed_stage else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
