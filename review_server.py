"""
Aider Code Review 中间件服务

接收Git平台Webhook，调用Aider进行代码审查，并将结果回写为评论
包含Web仪表盘和统计API
"""
import os
import shutil
import subprocess
import uuid
import json
import re
import time
from datetime import datetime
from typing import Optional

import requests
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from git import Repo
from sqlalchemy.orm import Session

from config import config
from utils import (
    logger, 
    parse_aider_output, 
    filter_valid_files,
    format_review_comment,
    get_commit_prompt,
    get_mr_prompt,
    sanitize_branch_name,
    convert_to_http_auth_url,
    build_git_auth
)
from database import init_database, get_db, get_db_session
from models import ReviewRecord, ReviewIssue, ReviewStatus, ReviewStrategy, IssueSeverity
from statistics import StatisticsService
from settings import SettingsManager
from polling import polling_manager, PollingRepo

app = FastAPI(
    title="Aider Code Review Service",
    description="基于Aider的自动化代码审查中间件",
    version=config.version
)

# 初始化数据库
init_database()

# 挂载静态文件
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ==================== 首页 ====================

@app.get("/")
async def index():
    """返回仪表盘首页"""
    index_path = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Aider Code Review Service", "version": config.version}


# ==================== 健康检查 ====================

@app.get("/health")
async def health_check():
    """健康检查接口"""
    # 使用动态配置
    settings = SettingsManager.get_all()
    return {
        "status": "healthy",
        "version": config.version,
        "vllm_endpoint": settings.get('vllm_api_base', config.vllm.api_base),
        "git_platform": settings.get('git_platform', config.git.platform)
    }


# ==================== 统计API ====================

@app.get("/api/stats/overview")
async def get_overview(db: Session = Depends(get_db)):
    """获取概览统计"""
    service = StatisticsService(db)
    return service.get_overview()


@app.get("/api/stats/daily-trend")
async def get_daily_trend(days: int = 30, db: Session = Depends(get_db)):
    """获取每日审查趋势"""
    service = StatisticsService(db)
    return service.get_daily_trend(days)


@app.get("/api/stats/authors")
async def get_authors(limit: int = 20, db: Session = Depends(get_db)):
    """获取提交人统计"""
    service = StatisticsService(db)
    return service.get_author_statistics(limit)


@app.get("/api/stats/author/{author_name}")
async def get_author_detail(author_name: str, db: Session = Depends(get_db)):
    """获取指定提交人详情"""
    service = StatisticsService(db)
    return service.get_author_detail(author_name)


@app.get("/api/stats/projects")
async def get_projects(limit: int = 20, db: Session = Depends(get_db)):
    """获取项目统计"""
    service = StatisticsService(db)
    return service.get_project_statistics(limit)


@app.get("/api/stats/reviews")
async def get_reviews(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """获取审查记录列表"""
    service = StatisticsService(db)
    return service.get_recent_reviews(limit, offset)


@app.get("/api/stats/review/{task_id}")
async def get_review_detail(task_id: str, db: Session = Depends(get_db)):
    """获取审查详情"""
    service = StatisticsService(db)
    result = service.get_review_detail(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Review not found")
    return result


@app.get("/api/stats/hotspots")
async def get_hotspots(limit: int = 20, db: Session = Depends(get_db)):
    """获取问题热点文件"""
    service = StatisticsService(db)
    return service.get_issue_hotspots(limit)


@app.get("/api/stats/categories")
async def get_categories(db: Session = Depends(get_db)):
    """获取问题类型分布"""
    service = StatisticsService(db)
    return service.get_issue_categories()


# ==================== 系统设置API ====================

@app.get("/api/settings")
async def get_settings():
    """获取所有系统设置"""
    return SettingsManager.get_all_with_meta()


@app.post("/api/settings")
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


@app.get("/api/settings/{key}")
async def get_setting(key: str):
    """获取单个设置"""
    value = SettingsManager.get(key)
    return {"key": key, "value": value}


@app.post("/api/settings/{key}")
async def set_setting(key: str, request: Request):
    """设置单个配置"""
    payload = await request.json()
    value = payload.get("value", "")
    
    success = SettingsManager.set(key, str(value))
    if success:
        return {"status": "success", "key": key, "value": value}
    else:
        raise HTTPException(status_code=500, detail="保存设置失败")


# ==================== 验证测试API ====================

@app.post("/api/test/git")
async def test_git_connection():
    """测试Git平台连接"""
    import time
    start_time = time.time()
    
    settings = SettingsManager.get_all()
    platform = settings.get('git_platform', 'gitlab')
    enable_comment = settings.get('enable_comment', 'true').lower() == 'true'
    
    # HTTP认证信息（用于克隆仓库）
    http_user = settings.get('git_http_user', '')
    http_password = settings.get('git_http_password', '')
    server_url = settings.get('git_server_url', '')
    
    # API信息（用于回写评论）
    api_url = settings.get('git_api_url', '')
    token = settings.get('git_token', '')
    
    results = []
    overall_success = True
    
    # 1. 验证HTTP认证配置（克隆仓库必需）
    if http_user and http_password and server_url:
        results.append("✓ HTTP认证已配置")
    else:
        missing = []
        if not http_user: missing.append("用户名")
        if not http_password: missing.append("密码")
        if not server_url: missing.append("服务器地址")
        results.append(f"⚠ HTTP认证缺少: {', '.join(missing)}")
    
    # 2. 如果启用了评论回写，验证API Token
    if enable_comment:
        if not api_url or not token:
            results.append("✗ 评论回写已启用但未配置API地址或Token")
            overall_success = False
        else:
            # 验证API连接
            try:
                if platform == 'gitlab':
                    url = f"{api_url}/user"
                    headers = {"PRIVATE-TOKEN": token}
                elif platform == 'gitea':
                    url = f"{api_url}/user"
                    headers = {"Authorization": f"token {token}"}
                elif platform == 'github':
                    url = f"{api_url}/user"
                    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
                else:
                    results.append(f"✗ 不支持的平台: {platform}")
                    overall_success = False
                    url = None
                
                if url:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    user_data = response.json()
                    username = user_data.get('username') or user_data.get('login') or user_data.get('name', 'Unknown')
                    results.append(f"✓ API连接成功 (用户: {username})")
                    
            except requests.exceptions.Timeout:
                results.append("✗ API连接超时")
                overall_success = False
            except requests.exceptions.ConnectionError:
                results.append("✗ 无法连接到API服务器")
                overall_success = False
            except requests.exceptions.HTTPError as e:
                results.append(f"✗ API认证失败: HTTP {e.response.status_code}")
                overall_success = False
            except Exception as e:
                results.append(f"✗ API测试失败: {str(e)}")
                overall_success = False
    else:
        results.append("ℹ 评论回写已关闭，跳过API验证")
    
    elapsed = round(time.time() - start_time, 2)
    
    return {
        "success": overall_success,
        "message": "配置验证完成" if overall_success else "部分配置有问题",
        "details": {
            "platform": platform,
            "enable_comment": enable_comment,
            "checks": results,
            "response_time": f"{elapsed}s"
        }
    }


@app.post("/api/test/vllm")
async def test_vllm_connection():
    """测试vLLM模型连接 - 发送真实对话验证"""
    import time
    start_time = time.time()
    
    settings = SettingsManager.get_all()
    api_base = settings.get('vllm_api_base', '')
    api_key = settings.get('vllm_api_key', '')
    model_name = settings.get('vllm_model_name', '')
    
    if not api_base:
        return {"success": False, "message": "vLLM API地址未配置", "details": {}}
    
    if not model_name:
        return {"success": False, "message": "模型名称未配置", "details": {}}
    
    try:
        # 发送真实的对话请求验证模型
        url = f"{api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # 构建简单的测试对话
        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": "Say 'Hello' in one word."}
            ],
            "max_tokens": 10,
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        elapsed = round(time.time() - start_time, 2)
        
        # 提取模型回复
        reply = ""
        if 'choices' in result and len(result['choices']) > 0:
            reply = result['choices'][0].get('message', {}).get('content', '')[:50]
        
        return {
            "success": True,
            "message": "模型对话成功",
            "details": {
                "api_base": api_base,
                "model": model_name,
                "reply": reply.strip(),
                "response_time": f"{elapsed}s"
            }
        }
    except requests.exceptions.Timeout:
        elapsed = round(time.time() - start_time, 2)
        return {"success": False, "message": f"模型响应超时 ({elapsed}s)", "details": {"api_base": api_base, "model": model_name}}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "无法连接到vLLM服务器", "details": {"api_base": api_base}}
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get('error', {}).get('message', str(e))[:100]
        except:
            error_detail = str(e)[:100]
        return {"success": False, "message": f"请求失败: {error_detail}", "details": {"api_base": api_base, "model": model_name}}
    except Exception as e:
        return {"success": False, "message": f"测试失败: {str(e)[:100]}", "details": {}}


@app.post("/api/test/aider")
async def test_aider():
    """测试Aider是否可用"""
    try:
        result = subprocess.run(
            ["aider", "--version"],
            capture_output=True,
            text=True,
            timeout=30  # 增加超时时间
        )
        
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            # 提取版本号
            version_match = re.search(r'[\d.]+', version)
            version_str = version_match.group(0) if version_match else version[:50]
            
            return {
                "success": True,
                "message": "Aider 可用",
                "details": {
                    "version": version_str
                }
            }
        else:
            # 提供更详细的错误信息
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            return {
                "success": False,
                "message": "Aider 运行失败",
                "details": {
                    "returncode": result.returncode,
                    "error": error_msg[:300] if error_msg else "Unknown error"
                }
            }
    except FileNotFoundError:
        return {"success": False, "message": "Aider 未安装", "details": {"hint": "请运行 pip install aider-chat"}}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Aider 响应超时", "details": {}}
    except Exception as e:
        return {"success": False, "message": f"测试失败: {str(e)}", "details": {}}


# ==================== 轮询管理API ====================

@app.get("/api/polling/status")
async def get_polling_status():
    """获取轮询状态"""
    return polling_manager.get_status()


@app.post("/api/polling/start")
async def start_polling():
    """启动轮询"""
    # 设置审查回调
    polling_manager.set_review_callback(run_aider_review)
    polling_manager.start()
    return {"status": "started", "message": "轮询已启动"}


@app.post("/api/polling/stop")
async def stop_polling():
    """停止轮询"""
    polling_manager.stop()
    return {"status": "stopped", "message": "轮询已停止"}


@app.get("/api/polling/repos")
async def get_polling_repos():
    """获取轮询仓库列表"""
    return {"repos": polling_manager.get_repos()}


@app.post("/api/polling/repos")
async def add_polling_repo(request: Request):
    """添加轮询仓库"""
    data = await request.json()
    
    # 生成唯一ID
    import uuid
    repo_id = str(uuid.uuid4())[:8]
    
    repo = PollingRepo(
        id=repo_id,
        name=data.get('name', '未命名仓库'),
        url=data.get('url', ''),
        branch=data.get('branch', 'main'),
        strategy=data.get('strategy', 'commit'),
        poll_commits=data.get('poll_commits', True),
        poll_mrs=data.get('poll_mrs', False),
        enabled=data.get('enabled', True),
    )
    
    if not repo.url:
        raise HTTPException(status_code=400, detail="仓库URL不能为空")
    
    polling_manager.add_repo(repo)
    return {"status": "added", "repo": repo.to_dict()}


@app.put("/api/polling/repos/{repo_id}")
async def update_polling_repo(repo_id: str, request: Request):
    """更新轮询仓库"""
    data = await request.json()
    
    success = polling_manager.update_repo(repo_id, data)
    if success:
        return {"status": "updated", "repo": polling_manager.get_repo(repo_id)}
    else:
        raise HTTPException(status_code=404, detail="仓库不存在")


@app.delete("/api/polling/repos/{repo_id}")
async def delete_polling_repo(repo_id: str):
    """删除轮询仓库"""
    success = polling_manager.remove_repo(repo_id)
    if success:
        return {"status": "deleted", "repo_id": repo_id}
    else:
        raise HTTPException(status_code=404, detail="仓库不存在")


@app.post("/api/polling/branches")
async def get_repo_branches(request: Request):
    """获取仓库分支列表"""
    data = await request.json()
    
    branches = polling_manager.get_branches(
        repo_url=data.get('url', ''),
        platform=data.get('platform', 'gitlab'),
        auth_type=data.get('auth_type', 'http_basic'),
        token=data.get('token', ''),
        http_user=data.get('http_user', ''),
        http_password=data.get('http_password', '')
    )
    
    return {"branches": branches}


@app.post("/api/polling/repos/{repo_id}/clone")
async def clone_repo(repo_id: str, background_tasks: BackgroundTasks):
    """克隆仓库到本地"""
    repo = polling_manager.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    # 后台执行克隆
    result = polling_manager.clone_repo(repo)
    return result


@app.post("/api/polling/parse-url")
async def parse_repo_url(request: Request):
    """解析仓库URL获取名称"""
    data = await request.json()
    url = data.get('url', '')
    
    # 从URL提取仓库名称
    import re
    
    # SSH格式: git@host:group/project.git
    ssh_match = re.match(r'git@[^:]+:(.+?)(?:\.git)?$', url)
    if ssh_match:
        path = ssh_match.group(1)
        name = path.split('/')[-1]
        return {"name": name, "path": path}
    
    # HTTP格式: http(s)://host/group/project.git
    http_match = re.match(r'https?://[^/]+/(.+?)(?:\.git)?$', url)
    if http_match:
        path = http_match.group(1)
        # 移除可能的用户名密码
        if '@' in path:
            path = path.split('@')[-1]
        name = path.split('/')[-1]
        return {"name": name, "path": path}
    
    return {"name": "", "path": ""}


# ==================== Webhook处理 ====================

@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    处理Git平台Webhook
    支持GitLab、Gitea、GitHub Enterprise
    """
    payload = await request.json()
    
    # 获取事件类型
    gitlab_event = request.headers.get("X-Gitlab-Event")
    gitea_event = request.headers.get("X-Gitea-Event")
    github_event = request.headers.get("X-GitHub-Event")
    
    event_type = gitlab_event or gitea_event or github_event
    
    if not event_type:
        logger.warning("未识别的Webhook事件")
        return {"status": "Ignored", "reason": "Unknown event type"}
    
    logger.info(f"收到Webhook事件: {event_type}")
    
    # GitLab事件处理
    if gitlab_event:
        return await handle_gitlab_event(gitlab_event, payload, background_tasks)
    
    # Gitea事件处理
    if gitea_event:
        return await handle_gitea_event(gitea_event, payload, background_tasks)
    
    # GitHub事件处理
    if github_event:
        return await handle_github_event(github_event, payload, background_tasks)
    
    return {"status": "Ignored"}


async def handle_gitlab_event(event_type: str, payload: dict, background_tasks: BackgroundTasks):
    """处理GitLab Webhook事件"""
    
    # Merge Request事件
    if event_type == "Merge Request Hook":
        attrs = payload.get('object_attributes', {})
        state = attrs.get('state')
        action = attrs.get('action')
        
        # 仅处理打开或更新的MR
        if state != 'opened' and action != 'update':
            return {"status": "Ignored", "reason": "MR not opened or updated"}
        
        # 提取提交人信息
        user = payload.get('user', {})
        
        context = {
            "project_id": str(payload['project']['id']),
            "project_name": payload['project'].get('name', ''),
            "mr_iid": attrs['iid'],
            "target_branch": attrs['target_branch'],
            "strategy": "merge_request",
            "platform": "gitlab",
            "author_name": user.get('name', user.get('username', '')),
            "author_email": user.get('email', ''),
        }
        repo_url = payload['project']['ssh_url']
        branch = attrs['source_branch']
        
        background_tasks.add_task(
            run_aider_review, repo_url, branch, "merge_request", context
        )
        logger.info(f"MR审查任务已提交: MR#{attrs['iid']}")
        return {"status": "Processing MR Review", "mr_iid": attrs['iid']}
    
    # Push事件
    elif event_type == "Push Hook":
        if payload.get('total_commits_count', 0) == 0:
            return {"status": "Ignored", "reason": "No commits in push"}
        
        latest_commit = payload['commits'][-1]
        
        context = {
            "project_id": str(payload['project_id']),
            "project_name": payload['project'].get('name', ''),
            "commit_id": latest_commit['id'],
            "strategy": "commit",
            "platform": "gitlab",
            "author_name": latest_commit.get('author', {}).get('name', ''),
            "author_email": latest_commit.get('author', {}).get('email', ''),
        }
        repo_url = payload['project']['ssh_url']
        branch = sanitize_branch_name(payload['ref'])
        
        background_tasks.add_task(
            run_aider_review, repo_url, branch, "commit", context
        )
        logger.info(f"Commit审查任务已提交: {latest_commit['id'][:8]}")
        return {"status": "Processing Commit Review", "commit_id": latest_commit['id']}
    
    return {"status": "Ignored", "reason": f"Unsupported event: {event_type}"}


async def handle_gitea_event(event_type: str, payload: dict, background_tasks: BackgroundTasks):
    """处理Gitea Webhook事件"""
    
    if event_type == "pull_request":
        action = payload.get('action')
        if action not in ['opened', 'synchronize']:
            return {"status": "Ignored", "reason": "PR action not supported"}
        
        pr = payload['pull_request']
        sender = payload.get('sender', {})
        
        context = {
            "repo_owner": payload['repository']['owner']['login'],
            "repo_name": payload['repository']['name'],
            "project_name": payload['repository']['full_name'],
            "pr_number": pr['number'],
            "target_branch": pr['base']['ref'],
            "strategy": "merge_request",
            "platform": "gitea",
            "author_name": sender.get('full_name', sender.get('login', '')),
            "author_email": sender.get('email', ''),
        }
        repo_url = payload['repository']['ssh_url']
        branch = pr['head']['ref']
        
        background_tasks.add_task(
            run_aider_review, repo_url, branch, "merge_request", context
        )
        return {"status": "Processing PR Review", "pr_number": pr['number']}
    
    elif event_type == "push":
        commits = payload.get('commits', [])
        if not commits:
            return {"status": "Ignored", "reason": "No commits"}
        
        latest_commit = commits[-1]
        pusher = payload.get('pusher', {})
        
        context = {
            "repo_owner": payload['repository']['owner']['login'],
            "repo_name": payload['repository']['name'],
            "project_name": payload['repository']['full_name'],
            "commit_id": latest_commit['id'],
            "strategy": "commit",
            "platform": "gitea",
            "author_name": latest_commit.get('author', {}).get('name', pusher.get('full_name', '')),
            "author_email": latest_commit.get('author', {}).get('email', pusher.get('email', '')),
        }
        repo_url = payload['repository']['ssh_url']
        branch = sanitize_branch_name(payload['ref'])
        
        background_tasks.add_task(
            run_aider_review, repo_url, branch, "commit", context
        )
        return {"status": "Processing Commit Review", "commit_id": latest_commit['id']}
    
    return {"status": "Ignored"}


async def handle_github_event(event_type: str, payload: dict, background_tasks: BackgroundTasks):
    """处理GitHub Webhook事件"""
    
    if event_type == "pull_request":
        action = payload.get('action')
        if action not in ['opened', 'synchronize']:
            return {"status": "Ignored", "reason": "PR action not supported"}
        
        pr = payload['pull_request']
        sender = payload.get('sender', {})
        
        context = {
            "repo_owner": payload['repository']['owner']['login'],
            "repo_name": payload['repository']['name'],
            "project_name": payload['repository']['full_name'],
            "pr_number": pr['number'],
            "target_branch": pr['base']['ref'],
            "strategy": "merge_request",
            "platform": "github",
            "author_name": sender.get('login', ''),
            "author_email": '',
        }
        repo_url = payload['repository']['ssh_url']
        branch = pr['head']['ref']
        
        background_tasks.add_task(
            run_aider_review, repo_url, branch, "merge_request", context
        )
        return {"status": "Processing PR Review", "pr_number": pr['number']}
    
    elif event_type == "push":
        commits = payload.get('commits', [])
        if not commits:
            return {"status": "Ignored", "reason": "No commits"}
        
        latest_commit = commits[-1]
        pusher = payload.get('pusher', {})
        
        context = {
            "repo_owner": payload['repository']['owner']['login'],
            "repo_name": payload['repository']['name'],
            "project_name": payload['repository']['full_name'],
            "commit_id": latest_commit['id'],
            "strategy": "commit",
            "platform": "github",
            "author_name": latest_commit.get('author', {}).get('name', pusher.get('name', '')),
            "author_email": latest_commit.get('author', {}).get('email', pusher.get('email', '')),
        }
        repo_url = payload['repository']['ssh_url']
        branch = sanitize_branch_name(payload['ref'])
        
        background_tasks.add_task(
            run_aider_review, repo_url, branch, "commit", context
        )
        return {"status": "Processing Commit Review", "commit_id": latest_commit['id']}
    
    return {"status": "Ignored"}


# ==================== 核心审查逻辑 ====================

def run_aider_review(repo_url: str, branch: str, strategy: str, context: dict):
    """
    核心执行逻辑：
    1. 创建审查记录
    2. 克隆代码到沙盒
    3. 运行Aider进行审查
    4. 解析输出并保存结果
    5. 回写评论到Git平台
    """
    task_id = str(uuid.uuid4())
    work_dir = os.path.join(config.server.work_dir_base, task_id)
    start_time = datetime.utcnow()
    
    logger.info(f"开始审查任务 {task_id}, 策略: {strategy}")
    
    # 创建审查记录
    with get_db_session() as db:
        record = ReviewRecord(
            task_id=task_id,
            strategy=ReviewStrategy.COMMIT if strategy == "commit" else ReviewStrategy.MERGE_REQUEST,
            status=ReviewStatus.PROCESSING,
            platform=context.get('platform', 'gitlab'),
            project_id=context.get('project_id'),
            project_name=context.get('project_name'),
            commit_id=context.get('commit_id'),
            mr_iid=context.get('mr_iid'),
            branch=branch,
            target_branch=context.get('target_branch'),
            author_name=context.get('author_name'),
            author_email=context.get('author_email'),
            started_at=start_time,
        )
        db.add(record)
        db.commit()
    
    try:
        # 1. 克隆代码到沙盒
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        
        # 从动态配置读取Git认证信息
        settings = SettingsManager.get_all()
        git_http_user = settings.get('git_http_user', '')
        git_http_password = settings.get('git_http_password', '')
        git_server_url = settings.get('git_server_url', '')
        
        # 转换为HTTP认证URL（如果配置了HTTP认证）
        clone_url = repo_url
        if git_http_user and git_http_password:
            clone_url = convert_to_http_auth_url(
                repo_url,
                git_http_user,
                git_http_password,
                git_server_url
            )
            logger.info(f"使用HTTP认证克隆仓库")
        
        logger.info(f"克隆仓库: {repo_url} -> {work_dir}")
        repo = Repo.clone_from(clone_url, work_dir)
        repo.git.checkout(branch)
        
        # 2. 根据策略获取变更文件和构建Prompt
        target_files = []
        prompt = ""
        
        if strategy == "commit":
            commit_id = context['commit_id']
            diff_files = repo.git.diff_tree(
                '--no-commit-id', '--name-only', '-r', commit_id
            ).splitlines()
            target_files = diff_files
            prompt = get_commit_prompt()
            logger.info(f"Commit {commit_id[:8]} 变更了 {len(diff_files)} 个文件")
            
        elif strategy == "merge_request":
            target_branch = context['target_branch']
            diff_files = repo.git.diff(
                '--name-only', f"origin/{target_branch}"
            ).splitlines()
            target_files = diff_files
            prompt = get_mr_prompt(target_branch)
            logger.info(f"MR相对于 {target_branch} 变更了 {len(diff_files)} 个文件")
        
        # 3. 过滤有效代码文件
        valid_files = filter_valid_files(target_files, config.aider.valid_extensions)
        
        # 更新文件数到数据库
        with get_db_session() as db:
            record = db.query(ReviewRecord).filter(ReviewRecord.task_id == task_id).first()
            if record:
                record.files_count = len(valid_files)
                record.files_reviewed = json.dumps(valid_files)
        
        if not valid_files:
            logger.warning("没有有效的代码文件需要审查")
            finalize_review(task_id, start_time, "ℹ️ 本次变更未包含需要审查的代码文件。", 0, 0, 0, 0)
            # 检查是否启用评论
            if SettingsManager.get_bool('enable_comment', True):
                post_comment_to_git(context, "ℹ️ 本次变更未包含需要审查的代码文件。")
            return
        
        logger.info(f"将审查 {len(valid_files)} 个代码文件: {valid_files}")
        
        # 4. 构造Aider命令 - 使用动态配置
        vllm_api_base = settings.get('vllm_api_base', config.vllm.api_base)
        vllm_api_key = settings.get('vllm_api_key', config.vllm.api_key)
        vllm_model_name = settings.get('vllm_model_name', config.vllm.model_name)
        aider_map_tokens = SettingsManager.get_int('aider_map_tokens', config.aider.map_tokens)
        aider_no_repo_map = SettingsManager.get_bool('aider_no_repo_map', config.aider.no_repo_map)
        
        env = os.environ.copy()
        env["OPENAI_API_BASE"] = vllm_api_base
        env["OPENAI_API_KEY"] = vllm_api_key
        env["AIDER_MODEL"] = vllm_model_name
        
        cmd = [
            "aider",
            "--no-auto-commits",
            "--no-git",
            "--yes",
            "--no-pretty",
            "--message", prompt,
        ]
        
        if aider_no_repo_map:
            cmd.append("--no-repo-map")
        else:
            cmd.extend(["--map-tokens", str(aider_map_tokens)])
        
        cmd.extend(valid_files)
        
        # 5. 执行Aider并捕获输出（支持重试）
        aider_timeout = SettingsManager.get_int('aider_timeout', 600)
        retry_count = SettingsManager.get_int('aider_retry_count', 1)
        
        logger.info(f"执行Aider命令: {' '.join(cmd[:6])}...")
        logger.info(f"使用模型: {vllm_model_name}, API: {vllm_api_base}")
        logger.info(f"超时: {aider_timeout}秒, 重试次数: {retry_count}")
        
        result = None
        last_error = None
        for attempt in range(retry_count + 1):
            try:
                result = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=aider_timeout
                )
                
                if result.returncode == 0:
                    break  # 成功，退出重试循环
                else:
                    last_error = result.stderr
                    if attempt < retry_count:
                        logger.warning(f"Aider执行失败 (尝试 {attempt + 1}/{retry_count + 1}), 准备重试...")
                        time.sleep(2)  # 等待2秒后重试
                    
            except subprocess.TimeoutExpired as e:
                last_error = f"执行超时 ({aider_timeout}秒)"
                if attempt < retry_count:
                    logger.warning(f"任务超时 (尝试 {attempt + 1}/{retry_count + 1}), 准备重试...")
                else:
                    raise e
        
        if result and result.returncode != 0:
            logger.error(f"Aider执行失败 (已重试{retry_count}次): {last_error}")
        
        # 6. 解析输出
        raw_output = result.stdout + result.stderr if result else ""
        review_report = parse_aider_output(raw_output)
        
        # 7. 分析问题数量
        critical, warning, suggestion = analyze_issues(review_report)
        total_issues = critical + warning + suggestion
        
        # 计算质量评分 (简单算法: 100 - 问题加权)
        quality_score = max(0, 100 - (critical * 20 + warning * 5 + suggestion * 1))
        
        # 8. 保存结果
        formatted_report = format_review_comment(review_report, strategy, context)
        finalize_review(task_id, start_time, formatted_report, total_issues, critical, warning, suggestion, quality_score)
        
        # 9. 回写评论（优先使用仓库级开关，fallback到全局配置）
        enable_comment = context.get('enable_comment', SettingsManager.get_bool('enable_comment', True))
        if enable_comment:
            post_comment_to_git(context, formatted_report)
        else:
            logger.info("评论回写已禁用，跳过")
        
        logger.info(f"任务 {task_id} 完成, 发现 {total_issues} 个问题")
        
    except subprocess.TimeoutExpired:
        logger.error(f"任务 {task_id} 超时 (已用尽所有重试)")
        finalize_review(task_id, start_time, None, 0, 0, 0, 0, error="任务超时")
        enable_comment = context.get('enable_comment', SettingsManager.get_bool('enable_comment', True))
        if enable_comment:
            post_comment_to_git(context, "⚠️ 代码审查超时，请稍后重试或减少变更文件数量。")
    except Exception as e:
        logger.exception(f"任务 {task_id} 执行失败: {e}")
        finalize_review(task_id, start_time, None, 0, 0, 0, 0, error=str(e))
        enable_comment = context.get('enable_comment', SettingsManager.get_bool('enable_comment', True))
        if enable_comment:
            post_comment_to_git(context, f"❌ 代码审查执行失败: {str(e)}")
    finally:
        if os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir)
                logger.info(f"清理工作目录: {work_dir}")
            except Exception as e:
                logger.warning(f"清理工作目录失败: {e}")


def finalize_review(task_id: str, start_time: datetime, report: Optional[str], 
                    issues: int, critical: int, warning: int, suggestion: int,
                    quality_score: float = None, error: str = None):
    """完成审查记录的更新"""
    end_time = datetime.utcnow()
    processing_time = (end_time - start_time).total_seconds()
    
    with get_db_session() as db:
        record = db.query(ReviewRecord).filter(ReviewRecord.task_id == task_id).first()
        if record:
            record.status = ReviewStatus.FAILED if error else ReviewStatus.COMPLETED
            record.completed_at = end_time
            record.processing_time_seconds = processing_time
            record.report = report
            record.issues_count = issues
            record.critical_count = critical
            record.warning_count = warning
            record.suggestion_count = suggestion
            record.quality_score = quality_score
            record.error_message = error


def analyze_issues(report: str) -> tuple:
    """分析审查报告中的问题数量"""
    if not report:
        return 0, 0, 0
    
    # 简单的问题识别逻辑，基于关键词
    critical = len(re.findall(r'🔴|严重|critical|error|security|漏洞|危险', report, re.IGNORECASE))
    warning = len(re.findall(r'🟡|警告|warning|注意|问题', report, re.IGNORECASE))
    suggestion = len(re.findall(r'🔵|建议|suggestion|优化|改进|recommend', report, re.IGNORECASE))
    
    return critical, warning, suggestion


def post_comment_to_git(context: dict, report: str):
    """回写评论到Git平台"""
    platform = context.get('platform', 'gitlab')
    
    # 优先使用仓库级认证信息，fallback到全局配置
    settings = SettingsManager.get_all()
    token = context.get('repo_token', '') or settings.get('git_token', '')
    http_user = context.get('repo_http_user', '') or settings.get('git_http_user', '')
    http_password = context.get('repo_http_password', '') or settings.get('git_http_password', '')
    api_url = settings.get('git_api_url', '')
    
    if not api_url:
        logger.warning("未配置Git API地址，无法回写评论")
        return
    
    # 构建认证信息
    auth_info = build_git_auth(platform, token, http_user, http_password)
    
    if not auth_info['headers'] and not auth_info['auth']:
        logger.warning("未配置认证信息（Token或HTTP用户名/密码），无法回写评论")
        return
    
    try:
        if platform == "gitlab":
            post_gitlab_comment(context, report, api_url, auth_info)
        elif platform == "gitea":
            post_gitea_comment(context, report, api_url, auth_info)
        elif platform == "github":
            post_github_comment(context, report, api_url, auth_info)
        else:
            logger.warning(f"不支持的Git平台: {platform}")
    except Exception as e:
        logger.exception(f"回写评论失败: {e}")


def post_gitlab_comment(context: dict, report: str, api_url: str, auth_info: dict):
    """发送GitLab评论"""
    from urllib.parse import quote
    
    # GitLab需要URL编码的project_id
    project_id = quote(context.get('project_id', ''), safe='')
    
    if context['strategy'] == 'merge_request':
        url = f"{api_url}/projects/{project_id}/merge_requests/{context['mr_iid']}/notes"
        response = requests.post(
            url, 
            headers=auth_info['headers'], 
            auth=auth_info['auth'],
            json={"body": report}
        )
        response.raise_for_status()
        logger.info(f"评论已发送到GitLab MR#{context['mr_iid']}")
    else:
        url = f"{api_url}/projects/{project_id}/repository/commits/{context['commit_id']}/comments"
        response = requests.post(
            url, 
            headers=auth_info['headers'],
            auth=auth_info['auth'],
            json={"note": report}
        )
        response.raise_for_status()
        logger.info(f"评论已发送到GitLab Commit {context['commit_id'][:8]}")


def post_gitea_comment(context: dict, report: str, api_url: str, auth_info: dict):
    """发送Gitea评论"""
    repo_owner = context.get('repo_owner', '')
    repo_name = context.get('repo_name', '')
    
    if not repo_owner or not repo_name:
        logger.warning("缺少repo_owner或repo_name，无法发送Gitea评论")
        return
    
    if context['strategy'] == 'merge_request':
        pr_number = context.get('pr_number', context.get('mr_iid'))
        url = f"{api_url}/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments"
        response = requests.post(
            url, 
            headers=auth_info['headers'],
            auth=auth_info['auth'],
            json={"body": report}
        )
        response.raise_for_status()
        logger.info(f"评论已发送到Gitea PR#{pr_number}")
    else:
        logger.warning("Gitea暂不支持Commit评论")


def post_github_comment(context: dict, report: str, api_url: str, auth_info: dict):
    """发送GitHub评论"""
    repo_owner = context.get('repo_owner', '')
    repo_name = context.get('repo_name', '')
    
    if not repo_owner or not repo_name:
        logger.warning("缺少repo_owner或repo_name，无法发送GitHub评论")
        return
    
    if context['strategy'] == 'merge_request':
        pr_number = context.get('pr_number', context.get('mr_iid'))
        url = f"{api_url}/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments"
        response = requests.post(
            url, 
            headers=auth_info['headers'],
            auth=auth_info['auth'],
            json={"body": report}
        )
        response.raise_for_status()
        logger.info(f"评论已发送到GitHub PR#{pr_number}")
    else:
        url = f"{api_url}/repos/{repo_owner}/{repo_name}/commits/{context['commit_id']}/comments"
        response = requests.post(
            url, 
            headers=auth_info['headers'],
            auth=auth_info['auth'],
            json={"body": report}
        )
        response.raise_for_status()
        logger.info(f"评论已发送到GitHub Commit {context['commit_id'][:8]}")


# ==================== 手动触发接口 ====================

@app.post("/review")
async def manual_review(request: Request, background_tasks: BackgroundTasks):
    """手动触发代码审查"""
    payload = await request.json()
    
    repo_url = payload.get('repo_url')
    branch = payload.get('branch')
    strategy = payload.get('strategy', 'commit')
    
    if not repo_url or not branch:
        raise HTTPException(status_code=400, detail="Missing repo_url or branch")
    
    context = {
        "strategy": strategy,
        "platform": payload.get('platform', 'gitlab'),
        "project_id": payload.get('project_id'),
        "project_name": payload.get('project_name', ''),
        "mr_iid": payload.get('mr_iid'),
        "commit_id": payload.get('commit_id'),
        "target_branch": payload.get('target_branch', 'main'),
        "repo_owner": payload.get('repo_owner'),
        "repo_name": payload.get('repo_name'),
        "pr_number": payload.get('pr_number'),
        "author_name": payload.get('author_name', 'Manual'),
        "author_email": payload.get('author_email', ''),
    }
    
    background_tasks.add_task(run_aider_review, repo_url, branch, strategy, context)
    
    return {"status": "Review task submitted", "strategy": strategy}


# ==================== 启动入口 ====================

@app.on_event("startup")
async def startup_event():
    """服务启动时自动恢复轮询状态"""
    polling_manager.auto_start_if_enabled(run_aider_review)

if __name__ == "__main__":
    import uvicorn
    
    # 使用动态配置显示启动信息
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
