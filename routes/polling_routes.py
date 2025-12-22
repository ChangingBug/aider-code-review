"""
轮询管理 API 路由
"""
import re
import uuid

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from polling import polling_manager, PollingRepo
from settings import SettingsManager
from utils import convert_to_http_auth_url, extract_project_path

# 导入核心审查函数 (延迟导入避免循环依赖)
def get_run_aider_review():
    from services.review import run_aider_review
    return run_aider_review

router = APIRouter(prefix="/api/polling", tags=["Polling"])


@router.get("/status")
async def get_polling_status():
    """获取轮询状态"""
    return polling_manager.get_status()


@router.get("/repos")
async def get_polling_repos():
    """获取轮询仓库列表"""
    return {"repos": polling_manager.get_repos()}


@router.post("/repos")
async def add_polling_repo(request: Request):
    """添加轮询仓库"""
    data = await request.json()
    
    # 生成唯一ID
    repo_id = str(uuid.uuid4())[:8]
    
    repo = PollingRepo(
        id=repo_id,
        name=data.get('name', '未命名仓库'),
        url=data.get('url', ''),
        branch=data.get('branch', 'main'),
        platform=data.get('platform', 'gitlab'),
        auth_type=data.get('auth_type', 'http_basic'),
        http_user=data.get('http_user', ''),
        http_password=data.get('http_password', ''),
        token=data.get('token', ''),
        api_url=data.get('api_url', ''),
        strategy=data.get('strategy', 'commit'),
        poll_commits=data.get('poll_commits', True),
        poll_mrs=data.get('poll_mrs', False),
        effective_time=data.get('effective_time', ''),
        webhook_commits=data.get('webhook_commits', True),
        webhook_mrs=data.get('webhook_mrs', True),
        webhook_branches=data.get('webhook_branches', ''),
        enable_comment=data.get('enable_comment', True),
        local_path=data.get('local_path', ''),
        enabled=data.get('enabled', True),
        trigger_mode=data.get('trigger_mode', 'polling'),
        webhook_secret=data.get('webhook_secret', ''),
        polling_interval=data.get('polling_interval', 5),
    )
    
    verify = data.get('verify', False)
    polling_manager.add_repo(repo, verify=verify)
    return {"status": "added", "repo": repo.to_dict()}


@router.post("/repos/test")
async def test_repo_connectivity(request: Request):
    """测试仓库连通性（保存前校验）"""
    data = await request.json()
    repo = PollingRepo(
        id=data.get('id', str(uuid.uuid4())[:8]),
        name=data.get('name', 'test'),
        url=data.get('url', ''),
        auth_type=data.get('auth_type', 'http_basic'),
        http_user=data.get('http_user', ''),
        http_password=data.get('http_password', ''),
        token=data.get('token', ''),
        platform=data.get('platform', 'gitlab')
    )
    
    if not repo.url:
        return {"success": False, "message": "仓库URL不能为空"}
        
    success, error = polling_manager.test_connectivity(repo)
    return {"success": success, "message": "连接成功" if success else error}


@router.post("/repos/verify-all")
async def verify_all_repos():
    """批量校验所有已添加仓库的连通性"""
    results = {}
    with polling_manager._repos_lock:
        repos = list(polling_manager._repos.values())
    
    for repo in repos:
        success, error = polling_manager.test_connectivity(repo)
        results[repo.id] = {
            "name": repo.name,
            "success": success,
            "message": "OK" if success else error
        }
    
    return {"status": "completed", "results": results}


@router.put("/repos/{repo_id}")
async def update_polling_repo(repo_id: str, request: Request):
    """更新轮询仓库"""
    data = await request.json()
    
    success = polling_manager.update_repo(repo_id, data)
    if success:
        return {"status": "updated", "repo": polling_manager.get_repo(repo_id)}
    else:
        raise HTTPException(status_code=404, detail="仓库不存在")


@router.delete("/repos/{repo_id}")
async def delete_polling_repo(repo_id: str):
    """删除轮询仓库"""
    success = polling_manager.remove_repo(repo_id)
    if success:
        return {"status": "deleted", "repo_id": repo_id}
    else:
        raise HTTPException(status_code=404, detail="仓库不存在")


@router.post("/branches")
async def get_repo_branches(request: Request):
    """获取仓库分支列表"""
    data = await request.json()
    
    branches = polling_manager.get_branches(
        repo_url=data.get('url', ''),
        platform=data.get('platform', 'gitlab'),
        auth_type=data.get('auth_type', 'http_basic'),
        token=data.get('token', ''),
        http_user=data.get('http_user', ''),
        http_password=data.get('http_password', ''),
        api_url=data.get('api_url', '')
    )
    
    return {"branches": branches}


@router.post("/repos/{repo_id}/clone")
async def clone_repo(repo_id: str, background_tasks: BackgroundTasks):
    """克隆仓库到本地"""
    repo = polling_manager.get_repo_obj(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    # 后台执行克隆
    result = polling_manager.clone_repo(repo)
    return result


@router.post("/repos/{repo_id}/trigger")
async def trigger_repo_review(repo_id: str, request: Request, background_tasks: BackgroundTasks):
    """手动触发仓库审查"""
    repo = polling_manager.get_repo_obj(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    if not repo.enabled:
        raise HTTPException(status_code=400, detail="仓库已禁用")
    
    # 获取审查类型（默认commit）
    try:
        data = await request.json()
        strategy = data.get('strategy', 'commit')
    except:
        strategy = 'commit'
    
    if strategy not in ['commit', 'merge_request']:
        strategy = 'commit'
    
    # 构建审查context
    settings = SettingsManager.get_all()
    git_server_url = settings.get('git_server_url', '')
    
    # 转换认证URL
    clone_url = repo.url
    if repo.auth_type == 'http_basic' and repo.http_user and repo.http_password:
        clone_url = convert_to_http_auth_url(
            repo.url,
            repo.http_user,
            repo.http_password,
            git_server_url
        )
    
    # 从URL提取项目路径
    project_path = extract_project_path(repo.url)
    path_parts = project_path.split('/') if project_path else []
    
    context = {
        'strategy': strategy,
        'platform': repo.platform,
        'project_id': project_path,
        'project_name': repo.name,
        'repo_owner': path_parts[0] if len(path_parts) >= 2 else '',
        'repo_name': path_parts[-1] if path_parts else repo.name,
        'author_name': 'Manual Trigger',
        'author_email': '',
        'local_path': repo.get_local_path(),
        'enable_comment': repo.enable_comment,
        'repo_token': repo.token,
        'repo_http_user': repo.http_user,
        'repo_http_password': repo.http_password,
        'repo_api_url': repo.api_url,
        'commit_id': 'HEAD',
        'target_branch': repo.branch,
    }
    
    # 后台执行审查
    run_aider_review = get_run_aider_review()
    background_tasks.add_task(run_aider_review, clone_url, repo.branch, strategy, context)
    
    strategy_text = 'Commit审查' if strategy == 'commit' else 'MR审查'
    return {"status": "triggered", "repo_id": repo_id, "strategy": strategy, "message": f"{strategy_text}任务已提交"}


@router.post("/parse-url")
async def parse_repo_url(request: Request):
    """解析仓库URL获取名称"""
    data = await request.json()
    url = data.get('url', '')
    
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
