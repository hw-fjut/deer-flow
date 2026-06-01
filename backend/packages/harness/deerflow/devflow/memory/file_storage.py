"""File system based memory storage implementation"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from deerflow.devflow.common.config import get_config
from deerflow.devflow.common.exceptions import MemoryStorageError
from deerflow.devflow.common.logging import setup_logger
from deerflow.devflow.memory.models import MemoryEntry, ProjectMemory, StageArtifact
from deerflow.devflow.memory.storage import MemoryStorage

logger = setup_logger("memory_storage")


class FileMemoryStorage(MemoryStorage):
    """File system based memory storage"""
    
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or get_config().memory_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._projects_cache: dict[str, ProjectMemory] = {}
    
    def _get_project_dir(self, project_id: str) -> Path:
        """Get project directory path"""
        return self.base_dir / project_id
    
    def _get_project_file(self, project_id: str) -> Path:
        """Get project memory file path"""
        return self._get_project_dir(project_id) / "project.json"
    
    def _get_artifacts_dir(self, project_id: str) -> Path:
        """Get artifacts directory path"""
        return self._get_project_dir(project_id) / "artifacts"
    
    def _get_artifact_file(self, project_id: str, stage: str) -> Path:
        """Get artifact file path"""
        return self._get_artifacts_dir(project_id) / f"{stage}.json"
    
    def _get_entries_dir(self, project_id: str) -> Path:
        """Get memory entries directory path"""
        return self._get_project_dir(project_id) / "entries"
    
    def _serialize_datetime(self, obj: Any) -> Any:
        """Serialize datetime object"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    async def save_project(self, project: ProjectMemory) -> str:
        """Save project memory to file system"""
        try:
            project_dir = self._get_project_dir(project.project_id)
            project_dir.mkdir(parents=True, exist_ok=True)
            
            project_data = {
                "project_id": project.project_id,
                "name": project.name,
                "description": project.description,
                "current_stage": project.current_stage,
                "artifacts": [a.__dict__ for a in project.artifacts],
                "context": project.context,
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat(),
            }
            
            project_file = self._get_project_file(project.project_id)
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(project_data, f, default=self._serialize_datetime, indent=2, ensure_ascii=False)
            
            self._projects_cache[project.project_id] = project
            logger.info(f"Saved project memory: {project.project_id}")
            return project.project_id
        except Exception as e:
            raise MemoryStorageError(f"Failed to save project: {e}")
    
    async def get_project(self, project_id: str) -> ProjectMemory | None:
        """Load project memory from file system"""
        if project_id in self._projects_cache:
            return self._projects_cache[project_id]
        
        project_file = self._get_project_file(project_id)
        if not project_file.exists():
            return None
        
        try:
            with open(project_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            project = ProjectMemory(
                project_id=data["project_id"],
                name=data["name"],
                description=data["description"],
                current_stage=data["current_stage"],
                artifacts=[StageArtifact(**a) for a in data.get("artifacts", [])],
                context=data.get("context", {}),
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
            )
            self._projects_cache[project_id] = project
            return project
        except Exception as e:
            raise MemoryStorageError(f"Failed to load project: {e}")
    
    async def save_artifact(self, artifact: StageArtifact) -> str:
        """Save stage artifact to file system"""
        try:
            artifacts_dir = self._get_artifacts_dir(artifact.project_id)
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            
            artifact_data = {
                "project_id": artifact.project_id,
                "stage": artifact.stage,
                "name": artifact.name,
                "content": artifact.content,
                "files": artifact.files,
                "metadata": artifact.metadata,
                "created_at": artifact.created_at.isoformat(),
            }
            
            artifact_file = self._get_artifact_file(artifact.project_id, artifact.stage)
            with open(artifact_file, "w", encoding="utf-8") as f:
                json.dump(artifact_data, f, default=self._serialize_datetime, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved artifact: {artifact.project_id}/{artifact.stage}")
            return f"{artifact.project_id}/{artifact.stage}"
        except Exception as e:
            raise MemoryStorageError(f"Failed to save artifact: {e}")
    
    async def get_artifact(self, project_id: str, stage: str) -> StageArtifact | None:
        """Load stage artifact from file system"""
        artifact_file = self._get_artifact_file(project_id, stage)
        if not artifact_file.exists():
            return None
        
        try:
            with open(artifact_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return StageArtifact(
                project_id=data["project_id"],
                stage=data["stage"],
                name=data["name"],
                content=data["content"],
                files=data.get("files", []),
                metadata=data.get("metadata", {}),
                created_at=datetime.fromisoformat(data["created_at"]),
            )
        except Exception as e:
            raise MemoryStorageError(f"Failed to load artifact: {e}")
    
    async def save_entry(self, entry: MemoryEntry) -> str:
        """Save memory entry to file system"""
        try:
            entry_id = entry.id or str(uuid.uuid4())[:8]
            entry.id = entry_id
            
            entries_dir = self._get_entries_dir(entry.project_id)
            entries_dir.mkdir(parents=True, exist_ok=True)
            
            entry_data = {
                "id": entry_id,
                "project_id": entry.project_id,
                "stage": entry.stage,
                "memory_type": entry.memory_type.value if hasattr(entry.memory_type, "value") else entry.memory_type,
                "content": entry.content,
                "metadata": entry.metadata,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
            }
            
            entry_file = entries_dir / f"{entry_id}.json"
            with open(entry_file, "w", encoding="utf-8") as f:
                json.dump(entry_data, f, default=self._serialize_datetime, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved memory entry: {entry_id}")
            return entry_id
        except Exception as e:
            raise MemoryStorageError(f"Failed to save entry: {e}")
    
    async def get_entries(self, project_id: str, stage: str | None = None) -> list[MemoryEntry]:
        """Load memory entries from file system"""
        entries_dir = self._get_entries_dir(project_id)
        if not entries_dir.exists():
            return []
        
        entries = []
        try:
            for entry_file in entries_dir.glob("*.json"):
                with open(entry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if stage and data.get("stage") != stage:
                    continue
                
                entries.append(MemoryEntry(
                    id=data["id"],
                    project_id=data["project_id"],
                    stage=data["stage"],
                    memory_type=data["memory_type"],
                    content=data["content"],
                    metadata=data.get("metadata", {}),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                ))
            
            return sorted(entries, key=lambda e: e.created_at)
        except Exception as e:
            raise MemoryStorageError(f"Failed to load entries: {e}")
