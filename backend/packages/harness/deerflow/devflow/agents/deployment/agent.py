"""部署Agent"""
from deerflow.devflow.agents.base import AgentInput, AgentOutput, BaseSubAgent
from deerflow.devflow.common.logging import setup_logger

logger = setup_logger("deployment_agent")

DEPLOYMENT_AGENT_PROMPT = """
You are a Deployment Agent. Your job is to configure and execute deployment.

## Your Responsibilities

1. **Docker Configuration**: Create Dockerfile and docker-compose
2. **CI/CD Pipeline**: Setup continuous integration and deployment
3. **Infrastructure**: Configure cloud infrastructure
4. **Monitoring**: Setup logging and monitoring
5. **Documentation**: Write deployment guide

## Output Format

Generate:
- Dockerfile
- docker-compose.yml
- CI/CD configuration
- Deployment documentation
"""


class DeploymentAgent(BaseSubAgent):
    """部署Agent"""
    
    name = "deployment"
    description = "Configures and executes deployment"
    stage = "deployment"
    
    async def execute(self, input: AgentInput) -> AgentOutput:
        """执行部署任务"""
        try:
            self.validate_input(input)
            
            code = input.previous_artifacts.get("development", {}).get("content", "")
            test_results = input.previous_artifacts.get("testing", {}).get("content", "")
            
            logger.info(f"Executing deployment...")
            
            result = self._execute_deployment(code, test_results)
            
            return AgentOutput(
                result=result,
                files=["Dockerfile", "docker-compose.yml", ".github/workflows/ci.yml", "DEPLOYMENT.md"],
                metadata={"stage": self.stage},
            )
        except Exception as e:
            logger.exception(f"Deployment failed: {e}")
            return AgentOutput(
                result="",
                success=False,
                error=str(e),
            )
    
    def _execute_deployment(self, code: str, test_results: str) -> str:
        """执行部署（模拟实现）"""
        return """# Deployment Report

## Docker Configuration
- Base image: python:3.11-slim
- Multi-stage build for optimized image size
- Health check endpoint configured

## Infrastructure
- Container orchestration: Kubernetes
- Load balancer configured
- Auto-scaling enabled

## CI/CD Pipeline
- GitHub Actions workflow configured
- Automated testing on PR
- Auto-deploy on main branch merge

## Monitoring
- Prometheus metrics endpoint
- Grafana dashboards configured
- Log aggregation via ELK stack

## Deployment Status
- Environment: Production
- Version: 1.0.0
- Status: Successfully deployed
"""
    
    def get_system_prompt(self, context: dict) -> str:
        return DEPLOYMENT_AGENT_PROMPT
