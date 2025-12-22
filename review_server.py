"""
Aider Code Review 服务入口

模块化架构：
- routes/: API 路由模块
- services/: 业务逻辑服务
"""
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict

from config import config
from database import init_database
from settings import SettingsManager
from utils import logger
from polling import polling_manager

# 创建 FastAPI 应用
app = FastAPI(
    title="Aider Code Review Service",
    description="基于Aider的自动化代码审查中间件",
    version=config.version
)

# 初始化数据库
init_database()

# ==================== 中间件 ====================

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 简单的请求速率限制
request_counts = defaultdict(lambda: {"count": 0, "reset_time": 0})
RATE_LIMIT = 100
RATE_WINDOW = 60


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """简单的速率限制中间件"""
    import time
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    rate_info = request_counts[client_ip]
    if current_time > rate_info["reset_time"]:
        rate_info["count"] = 0
        rate_info["reset_time"] = current_time + RATE_WINDOW
    
    rate_info["count"] += 1
    
    if rate_info["count"] > RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"}
        )
    
    return await call_next(request)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.exception(f"未捕获的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "error": str(exc)[:200]}
    )


# ==================== 静态文件 ====================

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    """返回仪表盘首页"""
    index_path = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Aider Code Review Service", "version": config.version}


# ==================== 注册路由 ====================

from routes.health import router as health_router
from routes.stats import router as stats_router
from routes.settings import router as settings_router
from routes.testing import router as testing_router
from routes.polling_routes import router as polling_router

app.include_router(health_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(testing_router)
app.include_router(polling_router)


# ==================== 启动事件 ====================

@app.on_event("startup")
async def startup_event():
    """服务启动时初始化"""
    # 导入核心审查函数并设置回调
    from services.review import run_aider_review
    polling_manager.set_review_callback(run_aider_review)
    logger.info("轮询审查回调已注册")


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    
    settings = SettingsManager.get_all()
    logger.info(f"启动Aider Code Review服务 v{config.version}")
    logger.info(f"vLLM端点: {settings.get('vllm_api_base', config.vllm.api_base)}")
    logger.info(f"Git平台: {settings.get('git_platform', config.git.platform)}")
    logger.info(f"仪表盘: http://{config.server.host}:{config.server.port}/")
    
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level.lower()
    )
