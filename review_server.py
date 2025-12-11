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
    convert_to_http_auth_url
)
from database import init_database, get_db, get_db_session
from models import ReviewRecord, ReviewIssue, ReviewStatus, ReviewStrategy, IssueSeverity
from statistics import StatisticsService
from settings import SettingsManager

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
        
        # 5. 执行Aider并捕获输出
        logger.info(f"执行Aider命令: {' '.join(cmd[:6])}...")
        logger.info(f"使用模型: {vllm_model_name}, API: {vllm_api_base}")
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode != 0:
            logger.error(f"Aider执行失败: {result.stderr}")
        
        # 6. 解析输出
        raw_output = result.stdout + result.stderr
        review_report = parse_aider_output(raw_output)
        
        # 7. 分析问题数量
        critical, warning, suggestion = analyze_issues(review_report)
        total_issues = critical + warning + suggestion
        
        # 计算质量评分 (简单算法: 100 - 问题加权)
        quality_score = max(0, 100 - (critical * 20 + warning * 5 + suggestion * 1))
        
        # 8. 保存结果
        formatted_report = format_review_comment(review_report, strategy, context)
        finalize_review(task_id, start_time, formatted_report, total_issues, critical, warning, suggestion, quality_score)
        
        # 9. 回写评论（根据开关决定）
        if SettingsManager.get_bool('enable_comment', True):
            post_comment_to_git(context, formatted_report)
        else:
            logger.info("评论回写已禁用，跳过")
        
        logger.info(f"任务 {task_id} 完成, 发现 {total_issues} 个问题")
        
    except subprocess.TimeoutExpired:
        logger.error(f"任务 {task_id} 超时")
        finalize_review(task_id, start_time, None, 0, 0, 0, 0, error="任务超时")
        post_comment_to_git(context, "⚠️ 代码审查超时，请稍后重试或减少变更文件数量。")
    except Exception as e:
        logger.exception(f"任务 {task_id} 执行失败: {e}")
        finalize_review(task_id, start_time, None, 0, 0, 0, 0, error=str(e))
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
    
    try:
        if platform == "gitlab":
            post_gitlab_comment(context, report)
        elif platform == "gitea":
            post_gitea_comment(context, report)
        elif platform == "github":
            post_github_comment(context, report)
        else:
            logger.warning(f"不支持的Git平台: {platform}")
    except Exception as e:
        logger.exception(f"回写评论失败: {e}")


def post_gitlab_comment(context: dict, report: str):
    """发送GitLab评论"""
    # 使用动态配置
    git_token = SettingsManager.get('git_token', config.git.token)
    git_api_url = SettingsManager.get('git_api_url', config.git.api_url)
    
    if not git_token:
        logger.warning("未配置Git Token，无法发送评论")
        return
    
    headers = {"PRIVATE-TOKEN": git_token}
    
    if context['strategy'] == 'merge_request':
        url = f"{git_api_url}/projects/{context['project_id']}/merge_requests/{context['mr_iid']}/notes"
        response = requests.post(url, headers=headers, json={"body": report})
        response.raise_for_status()
        logger.info(f"评论已发送到GitLab MR#{context['mr_iid']}")
    else:
        url = f"{git_api_url}/projects/{context['project_id']}/repository/commits/{context['commit_id']}/comments"
        response = requests.post(url, headers=headers, json={"note": report})
        response.raise_for_status()
        logger.info(f"评论已发送到GitLab Commit {context['commit_id'][:8]}")


def post_gitea_comment(context: dict, report: str):
    """发送Gitea评论"""
    git_token = SettingsManager.get('git_token', config.git.token)
    git_api_url = SettingsManager.get('git_api_url', config.git.api_url)
    
    if not git_token:
        logger.warning("未配置Git Token，无法发送评论")
        return
    
    headers = {"Authorization": f"token {git_token}"}
    
    if context['strategy'] == 'merge_request':
        url = f"{git_api_url}/repos/{context['repo_owner']}/{context['repo_name']}/issues/{context['pr_number']}/comments"
        response = requests.post(url, headers=headers, json={"body": report})
        response.raise_for_status()
        logger.info(f"评论已发送到Gitea PR#{context['pr_number']}")
    else:
        logger.warning("Gitea暂不支持Commit评论")


def post_github_comment(context: dict, report: str):
    """发送GitHub评论"""
    git_token = SettingsManager.get('git_token', config.git.token)
    git_api_url = SettingsManager.get('git_api_url', config.git.api_url)
    
    if not git_token:
        logger.warning("未配置Git Token，无法发送评论")
        return
    
    headers = {
        "Authorization": f"token {git_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    if context['strategy'] == 'merge_request':
        url = f"{git_api_url}/repos/{context['repo_owner']}/{context['repo_name']}/issues/{context['pr_number']}/comments"
        response = requests.post(url, headers=headers, json={"body": report})
        response.raise_for_status()
        logger.info(f"评论已发送到GitHub PR#{context['pr_number']}")
    else:
        url = f"{git_api_url}/repos/{context['repo_owner']}/{context['repo_name']}/commits/{context['commit_id']}/comments"
        response = requests.post(url, headers=headers, json={"body": report})
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
