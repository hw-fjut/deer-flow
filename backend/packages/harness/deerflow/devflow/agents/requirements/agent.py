"""需求分析Agent - 负责分析用户需求并生成PRD文档"""
from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("requirements_agent")

REQUIREMENTS_AGENT_PROMPT = """
You are a Requirements Analysis Agent. Your job is to analyze user input and produce a structured Product Requirements Document (PRD).

## Your Responsibilities

1. **Extract Core Requirements**: Identify functional and non-functional requirements from the description
2. **Write User Stories**: Create user stories in the format "As a [user], I want [action], so that [benefit]"
3. **Define Acceptance Criteria**: Specify clear, testable acceptance criteria for each requirement
4. **Prioritize Features**: Use MoSCoW method (Must have, Should have, Could have, Won't have)
5. **Identify Constraints**: Note any technical, budget, or time constraints

## Output Format

Generate a PRD with these sections:
- Executive Summary
- User Personas
- Functional Requirements
- Non-Functional Requirements
- User Stories
- Acceptance Criteria
- Priority Matrix
- Assumptions and Dependencies
"""


class RequirementsAgent(BaseSubAgent):
    """需求分析Agent"""
    
    name = "requirements"
    description = "Analyzes user requirements and generates PRD documents"
    stage = "requirements"
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        """执行需求分析任务"""
        try:
            self.validate_input(input)
            
            context_text = self.format_context(input.context)
            task = input.task
            
            logger.info(f"Executing requirements analysis for: {task[:50]}...")
            
            # TODO: 实际调用LLM进行需求分析
            # 这里使用模拟输出，实际应替换为真实的LLM调用
            result = self._analyze_requirements(task, context_text)
            
            return AgentOutput(
                result=result,
                files=["PRD.md"],
                metadata={"stage": self.stage},
            )
        except Exception as e:
            logger.exception(f"Requirements analysis failed: {e}")
            return AgentOutput(
                result="",
                success=False,
                error=str(e),
            )
    
    def _analyze_requirements(self, task: str, context: str) -> str:
        """分析需求并生成PRD（模拟实现）"""
        return f"""# Product Requirements Document

## Executive Summary
{task}

## User Personas
- Primary User: End users of the application
- Secondary User: Administrators and support staff

## Functional Requirements
1. Core functionality as described in the project
2. User authentication and authorization
3. Data management and persistence
4. User interface and experience

## Non-Functional Requirements
- Performance: Response time < 2 seconds
- Scalability: Support 1000+ concurrent users
- Availability: 99.9% uptime
- Security: OWASP Top 10 compliance

## User Stories
1. As a user, I want to create and manage my projects
2. As a user, I want to collaborate with team members
3. As an admin, I want to monitor system health

## Priority Matrix
| Feature | Priority | Effort |
|---------|----------|--------|
| Core functionality | Must | High |
| Authentication | Must | Medium |
| Collaboration | Should | High |
| Analytics | Could | Medium |
"""
    
    def get_system_prompt(self, context: dict) -> str:
        """获取系统提示词"""
        return REQUIREMENTS_AGENT_PROMPT
