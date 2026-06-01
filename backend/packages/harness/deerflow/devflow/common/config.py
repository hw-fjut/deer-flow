"""DevFlow 配置管理"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DevFlowConfig:
    """DevFlow 全局配置"""
    # 基础路径
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)
    data_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent / "data" / "devflow")
    log_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent / "logs")
    
    # Agent配置
    max_concurrent_agents: int = 3
    agent_timeout_seconds: int = 600
    
    # 记忆系统配置
    memory_backend: str = "filesystem"
    memory_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent / "data" / "devflow" / "memory")
    
    def __post_init__(self):
        """确保目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)


_config: DevFlowConfig | None = None


def get_config() -> DevFlowConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = DevFlowConfig()
    return _config


def set_config(config: DevFlowConfig) -> None:
    """设置全局配置"""
    global _config
    _config = config
