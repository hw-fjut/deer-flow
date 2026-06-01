"""架构设计Agent"""
from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("architecture_agent")

ARCHITECTURE_AGENT_PROMPT = """
You are an Architecture Design Agent. Your job is to design the technical architecture based on the PRD.

## Your Responsibilities

1. **System Design**: Design overall system architecture
2. **Technology Selection**: Choose appropriate technologies and frameworks
3. **Component Design**: Define system components and their interactions
4. **Data Model Design**: Design database schema and data flow
5. **API Design**: Define API endpoints and contracts
6. **Security Architecture**: Design security measures

## Output Format

Generate an Architecture Document with:
- System Architecture Diagram (text-based)
- Technology Stack
- Component Architecture
- Database Schema
- API Design
- Security Considerations
- Deployment Architecture
"""


class ArchitectureAgent(BaseSubAgent):
    """架构设计Agent"""
    
    name = "architecture"
    description = "Designs technical architecture based on requirements"
    stage = "architecture"
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        """执行架构设计任务"""
        try:
            self.validate_input(input)
            
            context_text = self.format_context(input.context)
            requirements = input.previous_artifacts.get("requirements", {}).get("content", "")
            
            logger.info(f"Executing architecture design...")
            
            result = self._design_architecture(requirements, context_text)
            
            return AgentOutput(
                result=result,
                files=["ARCHITECTURE.md"],
                metadata={"stage": self.stage},
            )
        except Exception as e:
            logger.exception(f"Architecture design failed: {e}")
            return AgentOutput(
                result="",
                success=False,
                error=str(e),
            )
    
    def _design_architecture(self, requirements: str, context: str) -> str:
        """设计架构（模拟实现）"""
        return """# Architecture Design Document

## System Architecture

```
+-------------+     +-------------+     +-------------+
|   Frontend  |---->|    API      |---->|   Database  |
|   (React)   |<----|   Server    |<----|   (Postgres)|
+-------------+     +-------------+     +-------------+
                           |
                    +------+------+
                    |   Cache     |
                    |   (Redis)   |
                    +-------------+
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React, TypeScript, TailwindCSS |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Cache | Redis |
| Message Queue | RabbitMQ |
| Deployment | Docker, Kubernetes |

## API Design

- RESTful API design
- OpenAPI/Swagger documentation
- JWT authentication

## Security

- HTTPS/TLS encryption
- Input validation and sanitization
- Rate limiting
- SQL injection prevention
"""
    
    def get_system_prompt(self, context: dict) -> str:
        return ARCHITECTURE_AGENT_PROMPT
