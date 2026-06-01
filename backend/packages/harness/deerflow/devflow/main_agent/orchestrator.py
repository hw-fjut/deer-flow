"""Task orchestrator - Main agent core logic"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from deerflow.devflow.agents.base import AgentInput, AgentOutput
from deerflow.devflow.common.exceptions import PipelineError, TaskOrchestrationError
from deerflow.devflow.common.logging import setup_logger
from deerflow.devflow.main_agent.prompt import MAIN_AGENT_PROMPT
from deerflow.devflow.main_agent.state import PipelineStage, PipelineStatus, PipelineState, StageResult
from deerflow.devflow.memory.models import MemoryType, ProjectMemory
from deerflow.devflow.memory.service import MemoryService

logger = setup_logger("orchestrator")


class DevFlowOrchestrator:
    """DevFlow task orchestrator"""
    
    def __init__(self, memory_service: MemoryService | None = None):
        self.memory = memory_service or MemoryService()
        self.active_pipelines: dict[str, PipelineState] = {}
    
    async def start_pipeline(self, name: str, description: str) -> PipelineState:
        """Start development pipeline"""
        project = await self.memory.create_project(name, description)
        
        state = PipelineState(
            project_id=project.project_id,
            name=name,
            description=description,
            status=PipelineStatus.RUNNING,
            started_at=datetime.now(),
        )
        
        self.active_pipelines[project.project_id] = state
        logger.info(f"Started pipeline: {name} ({project.project_id})")
        return state
    
    async def execute_pipeline(self, project_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Execute pipeline with streaming progress"""
        state = self.active_pipelines.get(project_id)
        if not state:
            raise TaskOrchestrationError(f"Pipeline not found: {project_id}")
        
        try:
            context = await self.memory.get_project_context(project_id)
            
            for stage in PipelineStage:
                if state.get_stage_result(stage):
                    continue
                
                state.current_stage = stage
                
                yield {
                    "type": "stage_start",
                    "project_id": project_id,
                    "stage": stage.value,
                    "timestamp": datetime.now().isoformat(),
                }
                
                result = await self._execute_stage(project_id, stage, context)
                
                if result.success:
                    state.mark_stage_completed(result)
                    
                    await self.memory.save_stage_artifact(
                        project_id=project_id,
                        stage=stage.value,
                        name=f"{stage.value}_output",
                        content=result.output,
                        files=result.files,
                    )
                    
                    context = await self.memory.get_project_context(project_id)
                    
                    yield {
                        "type": "stage_complete",
                        "project_id": project_id,
                        "stage": stage.value,
                        "output": result.output[:500],
                        "timestamp": datetime.now().isoformat(),
                    }
                else:
                    state.mark_failed(result)
                    yield {
                        "type": "stage_failed",
                        "project_id": project_id,
                        "stage": stage.value,
                        "error": result.error,
                        "timestamp": datetime.now().isoformat(),
                    }
                    return
            
            state.mark_completed()
            yield {
                "type": "pipeline_complete",
                "project_id": project_id,
                "status": state.to_dict(),
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            state.status = PipelineStatus.FAILED
            state.completed_at = datetime.now()
            yield {
                "type": "pipeline_error",
                "project_id": project_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    async def _execute_stage(self, project_id: str, stage: PipelineStage, context: dict[str, Any]) -> StageResult:
        """Execute a single stage"""
        started_at = datetime.now()
        
        try:
            agent = self._get_agent_for_stage(stage)
            
            agent_input = AgentInput(
                task=f"Execute {stage.value} stage for project: {context['name']}",
                context=context,
                previous_artifacts=context.get("artifacts", {}),
            )
            
            output = await agent.execute(agent_input)
            
            return StageResult(
                stage=stage,
                success=output.success,
                output=output.result,
                files=output.files,
                error=output.error,
                started_at=started_at,
            )
            
        except Exception as e:
            logger.exception(f"Stage {stage.value} failed: {e}")
            return StageResult(
                stage=stage,
                success=False,
                output="",
                error=str(e),
                started_at=started_at,
            )
    
    def _get_agent_for_stage(self, stage: PipelineStage):
        """Get sub-agent for stage"""
        from deerflow.devflow.agents.requirements.agent import RequirementsAgent
        from deerflow.devflow.agents.architecture.agent import ArchitectureAgent
        from deerflow.devflow.agents.development.agent import DevelopmentAgent
        from deerflow.devflow.agents.testing.agent import TestingAgent
        from deerflow.devflow.agents.deployment.agent import DeploymentAgent
        
        agent_map = {
            PipelineStage.REQUIREMENTS: RequirementsAgent(),
            PipelineStage.ARCHITECTURE: ArchitectureAgent(),
            PipelineStage.DEVELOPMENT: DevelopmentAgent(),
            PipelineStage.TESTING: TestingAgent(),
            PipelineStage.DEPLOYMENT: DeploymentAgent(),
        }
        
        return agent_map[stage]
    
    async def get_pipeline_status(self, project_id: str) -> PipelineState | None:
        """Get pipeline status"""
        state = self.active_pipelines.get(project_id)
        if not state:
            project = await self.memory.get_project(project_id)
            if not project:
                return None
            
            state = PipelineState(
                project_id=project_id,
                name=project.name,
                description=project.description,
                current_stage=PipelineStage(project.current_stage),
            )
            
            stages = ["requirements", "architecture", "development", "testing", "deployment"]
            for stage_name in stages:
                artifact = await self.memory.get_stage_artifact(project_id, stage_name)
                if artifact:
                    state.completed_stages.append(StageResult(
                        stage=PipelineStage(stage_name),
                        success=True,
                        output=artifact.content,
                        files=artifact.files,
                        completed_at=artifact.created_at,
                    ))
            
            self.active_pipelines[project_id] = state
        
        return state
    
    async def get_all_projects(self) -> list[dict[str, Any]]:
        """Get all projects list"""
        projects = []
        for project_id in list(self.active_pipelines.keys()):
            state = await self.get_pipeline_status(project_id)
            if state:
                projects.append(state.to_dict())
        return projects
