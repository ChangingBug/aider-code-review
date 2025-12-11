"""
动态配置管理模块
支持通过数据库存储配置，实现运行时修改、实时生效
"""
import os
from typing import Any, Dict, Optional
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 数据库路径
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "reviews.db"))

# 确保data目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 创建引擎和Base
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SettingsBase = declarative_base()


class SystemSetting(SettingsBase):
    """系统配置表"""
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    category = Column(String(50), nullable=True)  # git, vllm, aider, system
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# 默认配置值
DEFAULT_SETTINGS = {
    # Git 配置
    "git_platform": {"value": "gitlab", "category": "git", "description": "Git平台类型 (gitlab/gitea/github)"},
    "git_server_url": {"value": "http://code.kf.zjnx.net", "category": "git", "description": "Git服务器地址"},
    "git_http_user": {"value": "", "category": "git", "description": "HTTP认证用户名"},
    "git_http_password": {"value": "", "category": "git", "description": "HTTP认证密码"},
    "git_api_url": {"value": "http://code.kf.zjnx.net/api/v4", "category": "git", "description": "Git API地址"},
    "git_token": {"value": "", "category": "git", "description": "Git访问令牌"},
    "enable_comment": {"value": "true", "category": "git", "description": "是否回写评论到Git"},
    
    # vLLM 配置
    "vllm_api_base": {"value": "http://192.168.1.100:8000/v1", "category": "vllm", "description": "vLLM API地址"},
    "vllm_api_key": {"value": "sk-xxx", "category": "vllm", "description": "vLLM API密钥"},
    "vllm_model_name": {"value": "openai/qwen-2.5-coder-32b", "category": "vllm", "description": "模型名称"},
    
    # Aider 配置
    "aider_map_tokens": {"value": "262144", "category": "aider", "description": "RepoMap Token数量"},
    "aider_no_repo_map": {"value": "false", "category": "aider", "description": "是否禁用RepoMap"},
}


class SettingsManager:
    """动态配置管理器"""
    
    _session_factory = None
    _cache: Dict[str, str] = {}
    _cache_time: Optional[datetime] = None
    _cache_ttl = 5  # 缓存5秒
    
    @classmethod
    def _get_session(cls):
        """获取数据库会话"""
        if cls._session_factory is None:
            SettingsBase.metadata.create_all(engine)
            cls._session_factory = sessionmaker(bind=engine)
        return cls._session_factory()
    
    @classmethod
    def init_defaults(cls):
        """初始化默认配置"""
        session = cls._get_session()
        try:
            for key, info in DEFAULT_SETTINGS.items():
                existing = session.query(SystemSetting).filter(SystemSetting.key == key).first()
                if not existing:
                    setting = SystemSetting(
                        key=key,
                        value=info["value"],
                        category=info["category"],
                        description=info["description"]
                    )
                    session.add(setting)
            session.commit()
        finally:
            session.close()
    
    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """获取单个配置值"""
        all_settings = cls.get_all()
        return all_settings.get(key, default)
    
    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """获取布尔类型配置"""
        value = cls.get(key, str(default).lower())
        return value.lower() in ("true", "1", "yes", "on")
    
    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """获取整数类型配置"""
        try:
            return int(cls.get(key, str(default)))
        except ValueError:
            return default
    
    @classmethod
    def get_all(cls) -> Dict[str, str]:
        """获取所有配置（带缓存）"""
        now = datetime.utcnow()
        
        # 检查缓存是否有效
        if cls._cache_time and (now - cls._cache_time).total_seconds() < cls._cache_ttl:
            return cls._cache.copy()
        
        # 重新加载
        session = cls._get_session()
        try:
            settings = session.query(SystemSetting).all()
            cls._cache = {s.key: s.value or "" for s in settings}
            cls._cache_time = now
            return cls._cache.copy()
        finally:
            session.close()
    
    @classmethod
    def get_all_with_meta(cls) -> list:
        """获取所有配置（包含元数据）"""
        session = cls._get_session()
        try:
            settings = session.query(SystemSetting).order_by(SystemSetting.category, SystemSetting.key).all()
            return [
                {
                    "key": s.key,
                    "value": s.value or "",
                    "category": s.category or "other",
                    "description": s.description or "",
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None
                }
                for s in settings
            ]
        finally:
            session.close()
    
    @classmethod
    def set(cls, key: str, value: str) -> bool:
        """设置单个配置值"""
        session = cls._get_session()
        try:
            setting = session.query(SystemSetting).filter(SystemSetting.key == key).first()
            if setting:
                setting.value = value
                setting.updated_at = datetime.utcnow()
            else:
                # 新建配置
                default_info = DEFAULT_SETTINGS.get(key, {})
                setting = SystemSetting(
                    key=key,
                    value=value,
                    category=default_info.get("category", "other"),
                    description=default_info.get("description", "")
                )
                session.add(setting)
            session.commit()
            
            # 清除缓存
            cls._cache_time = None
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()
    
    @classmethod
    def set_many(cls, settings: Dict[str, str]) -> bool:
        """批量设置配置"""
        session = cls._get_session()
        try:
            for key, value in settings.items():
                setting = session.query(SystemSetting).filter(SystemSetting.key == key).first()
                if setting:
                    setting.value = value
                    setting.updated_at = datetime.utcnow()
                else:
                    default_info = DEFAULT_SETTINGS.get(key, {})
                    setting = SystemSetting(
                        key=key,
                        value=value,
                        category=default_info.get("category", "other"),
                        description=default_info.get("description", "")
                    )
                    session.add(setting)
            session.commit()
            
            # 清除缓存
            cls._cache_time = None
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()


# 初始化默认配置
SettingsManager.init_defaults()
