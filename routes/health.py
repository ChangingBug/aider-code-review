"""
健康检查路由
"""
from fastapi import APIRouter
from config import config
from settings import SettingsManager

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """健康检查接口"""
    settings = SettingsManager.get_all()
    return {
        "status": "healthy",
        "version": config.version,
        "vllm_endpoint": settings.get('vllm_api_base', config.vllm.api_base),
        "git_platform": settings.get('git_platform', config.git.platform)
    }
