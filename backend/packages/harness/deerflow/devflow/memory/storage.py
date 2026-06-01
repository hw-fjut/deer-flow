"""Memory storage abstract base class"""
from abc import ABC, abstractmethod
from typing import Any

from deerflow.devflow.memory.models import MemoryEntry, ProjectMemory, StageArtifact


class MemoryStorage(ABC):
    """Memory storage interface"""
    
    @abstractmethod
    async def save_project(self, project: ProjectMemory) -> str:
        """Save project memory
        
        Args:
            project: Project memory object
            
        Returns:
            project_id: Project ID
        """
        pass
    
    @abstractmethod
    async def get_project(self, project_id: str) -> ProjectMemory | None:
        """Get project memory
        
        Args:
            project_id: Project ID
            
        Returns:
            ProjectMemory object, or None if not found
        """
        pass
    
    @abstractmethod
    async def save_artifact(self, artifact: StageArtifact) -> str:
        """Save stage artifact
        
        Args:
            artifact: Stage artifact object
            
        Returns:
            artifact_id: Artifact ID
        """
        pass
    
    @abstractmethod
    async def get_artifact(self, project_id: str, stage: str) -> StageArtifact | None:
        """Get stage artifact
        
        Args:
            project_id: Project ID
            stage: Stage name
            
        Returns:
            StageArtifact object, or None if not found
        """
        pass
    
    @abstractmethod
    async def save_entry(self, entry: MemoryEntry) -> str:
        """Save memory entry
        
        Args:
            entry: Memory entry object
            
        Returns:
            entry_id: Entry ID
        """
        pass
    
    @abstractmethod
    async def get_entries(self, project_id: str, stage: str | None = None) -> list[MemoryEntry]:
        """Get memory entries
        
        Args:
            project_id: Project ID
            stage: Optional stage filter
            
        Returns:
            List of memory entries
        """
        pass
