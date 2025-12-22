"""
核心代码审查服务
"""
import os
import re
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from typing import Optional

from git import Repo

from config import config
from database import get_db_session
from models import ReviewRecord, ReviewStatus, ReviewStrategy
from settings import SettingsManager
from utils import (
    logger,
    parse_aider_output,
    filter_valid_files,
    format_review_comment,
    get_commit_prompt,
    get_mr_prompt,
    convert_to_http_auth_url,
    estimate_file_tokens,
    split_files_by_tokens,
    merge_batch_reports
)
from services.git_comment import post_comment_to_git


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
        
        # 优先使用仓库级认证信息
        settings = SettingsManager.get_all()
        git_http_user = context.get('repo_http_user') or settings.get('git_http_user', '')
        git_http_password = context.get('repo_http_password') or settings.get('git_http_password', '')
        git_token = context.get('repo_token') or settings.get('git_token', '')
        git_server_url = settings.get('git_server_url', '')
        
        # 转换为HTTP认证URL（支持用户名密码或Token）
        clone_url = repo_url
        if (git_http_user and git_http_password) or git_token:
            clone_url = convert_to_http_auth_url(
                repo_url,
                http_user=git_http_user,
                http_password=git_http_password,
                server_url=git_server_url,
                token=git_token
            )
            logger.info(f"使用Git认证信息克隆仓库")
        
        logger.info(f"克隆仓库: {repo_url} -> {work_dir}")
        repo = Repo.clone_from(clone_url, work_dir)
        repo.git.checkout(branch)
        
        # 2. 根据策略获取变更文件和构建Prompt
        target_files = []
        prompt = ""
        
        if strategy == "commit":
            commit_id = context['commit_id']
            
            # 检查生效时间 - 跳过在 effective_time 之前的提交
            effective_time_str = context.get('effective_time', '')
            if effective_time_str:
                try:
                    from datetime import datetime
                    # 获取 commit 时间
                    commit_time_str = repo.git.log('-1', '--format=%ci', commit_id)
                    commit_time = datetime.fromisoformat(commit_time_str.strip().replace(' ', 'T').replace(' +', '+'))
                    effective_time = datetime.fromisoformat(effective_time_str.replace('Z', '+00:00'))
                    
                    if commit_time < effective_time:
                        logger.info(f"Commit {commit_id[:8]} 时间 {commit_time} 早于生效时间 {effective_time}，跳过审查")
                        finalize_review(task_id, start_time, f"ℹ️ Commit 在生效时间之前，已跳过审查。", 0, 0, 0, 0)
                        return
                except Exception as e:
                    logger.warning(f"解析生效时间失败，继续审查: {e}")
            
            diff_files = repo.git.diff_tree(
                '--no-commit-id', '--name-only', '-r', commit_id
            ).splitlines()
            target_files = diff_files
            prompt = get_commit_prompt()
            logger.info(f"Commit {commit_id[:8]} 变更了 {len(diff_files)} 个文件")
            
        elif strategy == "merge_request":
            target_branch = context['target_branch']
            source_ref = context.get('source_ref', '')
            
            # Fetch 并 checkout 到 MR 源分支
            if source_ref:
                try:
                    # fetch MR 的源分支 ref
                    logger.info(f"Fetching MR source: {source_ref}")
                    repo.git.fetch('origin', f'{source_ref}:mr_branch')
                    repo.git.checkout('mr_branch')
                    logger.info(f"Checked out to MR source branch")
                except Exception as e:
                    logger.warning(f"Fetch MR source ref 失败，尝试使用当前分支: {e}")
            
            # 检查生效时间 - 跳过分支最新提交早于 effective_time 的 MR
            effective_time_str = context.get('effective_time', '')
            if effective_time_str:
                try:
                    from datetime import datetime
                    # 获取当前分支最新 commit 时间
                    commit_time_str = repo.git.log('-1', '--format=%ci')
                    commit_time = datetime.fromisoformat(commit_time_str.strip().replace(' ', 'T').replace(' +', '+'))
                    effective_time = datetime.fromisoformat(effective_time_str.replace('Z', '+00:00'))
                    
                    if commit_time < effective_time:
                        logger.info(f"MR 最新提交时间 {commit_time} 早于生效时间 {effective_time}，跳过审查")
                        finalize_review(task_id, start_time, f"ℹ️ MR 最新提交在生效时间之前，已跳过审查。", 0, 0, 0, 0)
                        return
                except Exception as e:
                    logger.warning(f"解析生效时间失败，继续审查: {e}")
            
            # 获取相对于目标分支的变更文件
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
        
        # 4. 获取配置
        vllm_api_base = settings.get('vllm_api_base', config.vllm.api_base)
        vllm_api_key = settings.get('vllm_api_key', config.vllm.api_key)
        vllm_model_name = settings.get('vllm_model_name', config.vllm.model_name)
        aider_map_tokens = SettingsManager.get_int('aider_map_tokens', config.aider.map_tokens)
        aider_no_repo_map = SettingsManager.get_bool('aider_no_repo_map', config.aider.no_repo_map)
        aider_timeout = SettingsManager.get_int('aider_timeout', 600)
        retry_count = SettingsManager.get_int('aider_retry_count', 1)
        
        # 分批配置（新增）
        aider_review_max_tokens = SettingsManager.get_int('aider_review_max_tokens', 100000)
        
        env = os.environ.copy()
        env["OPENAI_API_BASE"] = vllm_api_base
        env["OPENAI_API_KEY"] = vllm_api_key
        env["AIDER_MODEL"] = vllm_model_name
        
        # 5. 计算是否需要分批
        total_tokens = sum(estimate_file_tokens(os.path.join(work_dir, f)) for f in valid_files)
        
        if total_tokens > aider_review_max_tokens:
            logger.info(f"总 token 数 {total_tokens} 超出限制 {aider_review_max_tokens}，启用分批审查")
            batches = split_files_by_tokens(valid_files, work_dir, aider_review_max_tokens)
            logger.info(f"文件已分为 {len(batches)} 批")
        else:
            batches = [valid_files]
            logger.info(f"总 token 数 {total_tokens}，无需分批")
        
        # 更新批次总数到数据库
        with get_db_session() as db:
            record = db.query(ReviewRecord).filter(ReviewRecord.task_id == task_id).first()
            if record:
                record.batch_total = len(batches)
                record.batch_current = 0
        
        # 6. 多批次执行 Aider（保留 Repo Map 全仓库感知）
        batch_reports = []
        batch_results_summary = []  # 用于存储每批次摘要
        
        for batch_idx, batch_files in enumerate(batches):
            logger.info(f"执行批次 {batch_idx + 1}/{len(batches)}: {len(batch_files)} 个文件")
            
            # 更新当前批次进度
            with get_db_session() as db:
                record = db.query(ReviewRecord).filter(ReviewRecord.task_id == task_id).first()
                if record:
                    record.batch_current = batch_idx + 1

            
            # 构造 Aider 命令
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
                cmd.extend(["--map-tokens", str(aider_map_tokens)])  # 保留 Repo Map
            
            cmd.extend(batch_files)
            
            logger.info(f"使用模型: {vllm_model_name}, API: {vllm_api_base}")
            
            # 执行并重试
            result = None
            last_error = None
            batch_success = True
            
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
                        break
                    else:
                        last_error = result.stderr
                        # 记录详细错误信息用于诊断
                        logger.warning(f"批次 {batch_idx + 1} 失败 (尝试 {attempt + 1}/{retry_count + 1})")
                        logger.warning(f"returncode: {result.returncode}")
                        logger.warning(f"stderr: {result.stderr[:500] if result.stderr else '(空)'}")
                        if attempt < retry_count:
                            logger.info(f"等待 2 秒后重试...")
                            time.sleep(2)

                        
                except subprocess.TimeoutExpired:
                    last_error = f"执行超时 ({aider_timeout}秒)"
                    if attempt < retry_count:
                        logger.warning(f"批次 {batch_idx + 1} 超时 (尝试 {attempt + 1}/{retry_count + 1}), 重试...")
                    else:
                        # 超时用尽重试后，记录错误但继续后续批次
                        logger.error(f"批次 {batch_idx + 1} 超时失败，跳过此批次继续执行")
                        batch_success = False
            
            # 解析批次输出
            if batch_success and result:
                raw_output = result.stdout + result.stderr
                batch_report = parse_aider_output(raw_output)
                batch_status = 'success'
            else:
                batch_report = f"⚠️ 批次 {batch_idx + 1} 执行失败: {last_error}"
                batch_status = 'failed'
            
            batch_reports.append((batch_files, batch_report))
            
            # 记录批次摘要
            batch_results_summary.append({
                'batch': batch_idx + 1,
                'files': batch_files[:3],  # 只记录前3个文件名
                'files_count': len(batch_files),
                'status': batch_status,
                'preview': batch_report[:200] if batch_report else ''  # 预览前200字符
            })
            
            # 更新批次结果到数据库
            with get_db_session() as db:
                record = db.query(ReviewRecord).filter(ReviewRecord.task_id == task_id).first()
                if record:
                    record.batch_results = json.dumps(batch_results_summary, ensure_ascii=False)
            
            if result and result.returncode != 0:
                logger.warning(f"批次 {batch_idx + 1} 返回非零状态: {last_error}")

        
        # 7. 合并报告
        if len(batch_reports) > 1:
            review_report = merge_batch_reports(batch_reports)
            logger.info(f"已合并 {len(batch_reports)} 个批次的报告")
        else:
            review_report = batch_reports[0][1] if batch_reports else "⚠️ 未获取到审查结果"

        
        # 8. 分析问题数量
        critical, warning, suggestion = analyze_issues(review_report)
        total_issues = critical + warning + suggestion
        
        # 计算质量评分 (简单算法: 100 - 问题加权)
        quality_score = max(0, 100 - (critical * 20 + warning * 5 + suggestion * 1))
        
        # 9. 保存结果
        formatted_report = format_review_comment(review_report, strategy, context)
        finalize_review(task_id, start_time, formatted_report, total_issues, critical, warning, suggestion, quality_score)
        
        # 10. 回写评论（优先使用仓库级开关，fallback到全局配置）
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
