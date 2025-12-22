"""
系统设置 API 路由
"""
from fastapi import APIRouter, Request, HTTPException

from settings import SettingsManager

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("")
async def get_settings():
    """获取所有系统设置"""
    return SettingsManager.get_all_with_meta()


@router.post("")
async def update_settings(request: Request):
    """更新系统设置"""
    payload = await request.json()
    
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload format")
    
    success = SettingsManager.set_many(payload)
    if success:
        return {"status": "success", "message": "设置已保存"}
    else:
        raise HTTPException(status_code=500, detail="保存设置失败")


@router.get("/{key}")
async def get_setting(key: str):
    """获取单个设置"""
    value = SettingsManager.get(key)
    return {"key": key, "value": value}


@router.post("/{key}")
async def set_setting(key: str, request: Request):
    """设置单个配置"""
    payload = await request.json()
    value = payload.get("value", "")
    
    success = SettingsManager.set(key, str(value))
    if success:
        return {"status": "success", "key": key, "value": value}
    else:
        raise HTTPException(status_code=500, detail="保存设置失败")
