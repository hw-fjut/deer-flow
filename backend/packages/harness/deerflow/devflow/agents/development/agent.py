"""代码开发Agent"""
from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("development_agent")

DEVELOPMENT_AGENT_PROMPT = """
You are a Code Development Agent. Your job is to implement the actual code based on requirements and architecture.

## Your Responsibilities

1. **Project Setup**: Initialize project structure and dependencies
2. **Core Implementation**: Write clean, maintainable code
3. **Best Practices**: Follow coding standards and design patterns
4. **Documentation**: Add inline comments and docstrings
5. **Code Review**: Self-review for potential issues

## Output Format

Generate:
- Complete source code files
- Configuration files
- README with setup instructions
"""


class DevelopmentAgent(BaseSubAgent):
    """代码开发Agent"""
    
    name = "development"
    description = "Implements code based on requirements and architecture"
    stage = "development"
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        """执行代码开发任务"""
        try:
            self.validate_input(input)
            
            requirements = input.previous_artifacts.get("requirements", {}).get("content", "")
            architecture = input.previous_artifacts.get("architecture", {}).get("content", "")
            
            logger.info(f"Executing code development...")
            
            result = self._develop_code(requirements, architecture)
            
            return AgentOutput(
                result=result,
                files=["main.py", "config.py", "models/", "services/", "api/"],
                metadata={"stage": self.stage},
            )
        except Exception as e:
            logger.exception(f"Code development failed: {e}")
            return AgentOutput(
                result="",
                success=False,
                error=str(e),
            )
    
    def _develop_code(self, requirements: str, architecture: str) -> str:
        """开发代码（模拟实现）"""
        return """# Development Output

## Project Structure
```
project/
+-- src/
|   +-- main.py
|   +-- config.py
|   +-- models/
|   +-- services/
+-- tests/
+-- requirements.txt
+-- README.md
```

## Key Implementation Details
- FastAPI for API server
- SQLAlchemy for ORM
- Pydantic for data validation
- Alembic for migrations
"""
    
    def get_system_prompt(self, context: dict) -> str:
        return DEVELOPMENT_AGENT_PROMPT
