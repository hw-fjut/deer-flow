"""Memory service - High-level API provider"""
import uuid
from datetime import datetime
from typing import Any

from deerflow.devflow.common.exceptions import MemoryStorageError
from deerflow.devflow.common.logging import setup_logger
from deerflow.devflow.memory.file_storage import FileMemoryStorage
from deerflow.devflow.memory.models import MemoryEntry, MemoryType, ProjectMemory, StageArtifact
from deerflow.devflow.memory.storage import MemoryStorage

logger = setup_logger("memory_service")


class MemoryService:
    """Memory service providing high-level API"""
    
    def __init__(self, storage: MemoryStorage | None = None):
        self.storage = storage or FileMemoryStorage()
    
    async def create_project(self, name: str, description: str) -> ProjectMemory:
        """Create new project"""
        project_id = str(uuid.uuid4())[:8]
        project = ProjectMemory(
            project_id=project_id,
            name=name,
            description=description,
            current_stage="requirements",
        )
        await self.storage.save_project(project)
        logger.info(f"Created project: {name} ({project_id})")
        return project
    
    async def get_project(self, project_id: str) -> ProjectMemory | None:
        """Get project memory"""
        return await self.storage.get_project(project_id)
    
    async def save_stage_artifact(self, project_id: str, stage: str, name: str, content: str,
                                   files: list[str] | None = None, metadata: dict[str, Any] | None = None) -> StageArtifact:
        """Save stage artifact"""
        artifact = StageArtifact(
            project_id=project_id,
            stage=stage,
            name=name,
            content=content,
            files=files or [],
            metadata=metadata or {},
        )
        await self.storage.save_artifact(artifact)
        logger.info(f"Saved artifact for {project_id}/{stage}")
        return artifact
    
    async def get_stage_artifact(self, project_id: str, stage: str) -> StageArtifact | None:
        """Get stage artifact"""
        return await self.storage.get_artifact(project_id, stage)
    
    async def add_memory_entry(self, project_id: str, stage: str, memory_type: MemoryType,
                                content: str, metadata: dict[str, Any] | None = None) -> MemoryEntry:
        """Add memory entry"""
        entry = MemoryEntry(
            project_id=project_id,
            stage=stage,
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
        )
        entry_id = await self.storage.save_entry(entry)
        logger.info(f"Added memory entry: {entry_id}")
        return entry
    
    async def get_memory_entries(self, project_id: str, stage: str | None = None) -> list[MemoryEntry]:
        """Get memory entries"""
        return await self.storage.get_entries(project_id, stage)
    
    async def get_project_context(self, project_id: str) -> dict[str, Any]:
        """Get complete project context for agent calls"""
        project = await self.get_project(project_id)
        if not project:
            raise MemoryStorageError(f"Project not found: {project_id}")
        
        context = {
            "project_id": project_id,
            "name": project.name,
            "description": project.description,
            "current_stage": project.current_stage,
            "artifacts": {},
            "entries": [],
        }
        
        # Load all stage artifacts. Order matches the pipeline declaration
        # (linear head + loop subgraph).
        stages = [
            "requirements",
            "frontend_design",
            "spec_development",
            "code_testing",
            "deployment",
            # Legacy stages kept for backwards compatibility with the
            # pre-loop project format.
            "architecture",
            "development",
            "testing",
        ]
        for stage in stages:
            artifact = await self.get_stage_artifact(project_id, stage)
            if artifact:
                context["artifacts"][stage] = {
                    "name": artifact.name,
                    "content": artifact.content,
                    "files": artifact.files,
                    "metadata": artifact.metadata,
                }
        
        # Load memory entries
        entries = await self.get_memory_entries(project_id)
        context["entries"] = [
            {
                "id": e.id,
                "stage": e.stage,
                "type": e.memory_type,
                "content": e.content,
                "metadata": e.metadata,
            }
            for e in entries
        ]
        
        return context
    
    async def advance_stage(self, project_id: str, new_stage: str) -> ProjectMemory:
        """Advance project stage"""
        project = await self.get_project(project_id)
        if not project:
            raise MemoryStorageError(f"Project not found: {project_id}")
        
        project.update_stage(new_stage)
        await self.storage.save_project(project)
        logger.info(f"Advanced project {project_id} to stage: {new_stage}")
        return project
