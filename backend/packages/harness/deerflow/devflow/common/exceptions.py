"""公共异常定义"""


class DevFlowError(Exception):
    """DevFlow base error"""
    def __init__(self, message: str, code: str = "DEVFLOW_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class AgentNotFoundError(DevFlowError):
    """Agent not found error"""
    def __init__(self, agent_name: str):
        super().__init__(f"Agent not found: {agent_name}", "AGENT_NOT_FOUND")


class MemoryStorageError(DevFlowError):
    """Memory storage error"""
    def __init__(self, message: str):
        super().__init__(message, "MEMORY_STORAGE_ERROR")


class TaskOrchestrationError(DevFlowError):
    """Task orchestration error"""
    def __init__(self, message: str):
        super().__init__(message, "TASK_ORCHESTRATION_ERROR")


class PipelineError(DevFlowError):
    """Pipeline execution error"""
    def __init__(self, stage: str, message: str):
        super().__init__(f"Stage '{stage}' failed: {message}", "PIPELINE_ERROR")
        self.stage = stage
