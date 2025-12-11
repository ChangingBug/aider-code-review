"""
配置管理模块
支持通过环境变量覆盖默认配置
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class VLLMConfig:
    """vLLM服务配置"""
    api_base: str = field(default_factory=lambda: os.getenv("VLLM_API_BASE", "http://192.168.1.100:8000/v1"))
    api_key: str = field(default_factory=lambda: os.getenv("VLLM_API_KEY", "sk-xxx"))
    # 使用openai/前缀欺骗Aider使用OpenAI协议
    model_name: str = field(default_factory=lambda: os.getenv("VLLM_MODEL_NAME", "openai/qwen-2.5-coder-32b"))


@dataclass
class GitConfig:
    """Git平台配置"""
    token: str = field(default_factory=lambda: os.getenv("GIT_TOKEN", ""))
    api_url: str = field(default_factory=lambda: os.getenv("GIT_API_URL", "http://gitlab.internal/api/v4"))
    platform: str = field(default_factory=lambda: os.getenv("GIT_PLATFORM", "gitlab"))  # gitlab, gitea, github
    # HTTP认证配置（用于克隆仓库）
    http_user: str = field(default_factory=lambda: os.getenv("GIT_HTTP_USER", ""))
    http_password: str = field(default_factory=lambda: os.getenv("GIT_HTTP_PASSWORD", ""))
    # Git服务器基础URL（用于URL转换）
    server_url: str = field(default_factory=lambda: os.getenv("GIT_SERVER_URL", ""))


@dataclass
class AiderConfig:
    """Aider配置"""
    map_tokens: int = field(default_factory=lambda: int(os.getenv("AIDER_MAP_TOKENS", "2048")))
    no_repo_map: bool = field(default_factory=lambda: os.getenv("AIDER_NO_REPO_MAP", "false").lower() == "true")
    # 支持的代码文件扩展名
    valid_extensions: List[str] = field(default_factory=lambda: [
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.java', '.go', '.cpp', '.c', '.h',
        '.rs', '.rb', '.php', '.cs', '.swift',
        '.kt', '.scala', '.vue', '.svelte'
    ])


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("SERVER_PORT", "5000")))
    work_dir_base: str = field(default_factory=lambda: os.getenv("WORK_DIR_BASE", "/tmp/aider_reviewer"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


@dataclass
class AppConfig:
    """应用总配置"""
    vllm: VLLMConfig = field(default_factory=VLLMConfig)
    git: GitConfig = field(default_factory=GitConfig)
    aider: AiderConfig = field(default_factory=AiderConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    version: str = "1.0.0"


# 全局配置实例
config = AppConfig()
