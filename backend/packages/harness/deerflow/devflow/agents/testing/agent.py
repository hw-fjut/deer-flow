"""测试Agent"""
from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("testing_agent")

TESTING_AGENT_PROMPT = """
You are a Testing Agent. Your job is to write and execute tests for the developed code.

## Your Responsibilities

1. **Unit Tests**: Write unit tests for individual components
2. **Integration Tests**: Write tests for component interactions
3. **E2E Tests**: Write end-to-end tests for complete workflows
4. **Test Coverage**: Ensure adequate test coverage
5. **Bug Reporting**: Report any issues found

## Output Format

Generate:
- Test files
- Test execution report
- Coverage report
"""


class TestingAgent(BaseSubAgent):
    """测试Agent"""
    
    name = "testing"
    description = "Writes and executes tests for the developed code"
    stage = "testing"
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        """执行测试任务"""
        try:
            self.validate_input(input)
            
            code = input.previous_artifacts.get("development", {}).get("content", "")
            
            logger.info(f"Executing testing...")
            
            result = self._execute_tests(code)
            
            return AgentOutput(
                result=result,
                files=["tests/test_main.py", "tests/test_services.py", "coverage_report.html"],
                metadata={"stage": self.stage},
            )
        except Exception as e:
            logger.exception(f"Testing failed: {e}")
            return AgentOutput(
                result="",
                success=False,
                error=str(e),
            )
    
    def _execute_tests(self, code: str) -> str:
        """执行测试（模拟实现）"""
        return """# Test Report

## Test Results
| Test Suite | Tests | Passed | Failed | Skipped |
|------------|-------|--------|--------|---------|
| Unit Tests | 25 | 25 | 0 | 0 |
| Integration Tests | 10 | 10 | 0 | 0 |
| E2E Tests | 5 | 5 | 0 | 0 |

## Coverage
- Line Coverage: 85%
- Branch Coverage: 78%
- Function Coverage: 92%

All tests passed successfully.
"""
    
    def get_system_prompt(self, context: dict) -> str:
        return TESTING_AGENT_PROMPT
