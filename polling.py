"""
轮询管理器模块
定时轮询 Git 仓库，检查新提交和 MR，自动触发代码审查
"""
import threading
import time
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
import requests

from settings import SettingsManager
from utils import logger, convert_to_http_auth_url, extract_project_path


@dataclass
class PollingRepo:
    """轮询仓库配置"""
    id: str
    name: str
    url: str                      # 仓库URL (HTTP格式)
    branch: str = "main"          # 监控的分支
    
    # 平台和认证配置（仓库级别）
    platform: str = "gitlab"      # Git平台类型: gitlab / gitea / github
    auth_type: str = "http_basic" # 鉴权方式: token / http_basic
    http_user: str = ""           # HTTP认证用户名
    http_password: str = ""       # HTTP认证密码
    token: str = ""               # API Token
    api_url: str = ""             # Git API地址（仓库级别，如 http://code.example.com/api/v4）
    
    # 存储配置
    local_path: str = ""          # 本地存储路径，默认 /app/repos/{name}/{branch}
    
    # 轮询模式配置（独立）
    strategy: str = "commit"      # 审查策略: commit / mr
    poll_commits: bool = True     # 是否轮询新提交
    poll_mrs: bool = False        # 是否轮询新MR
    effective_time: str = ""      # 生效时间，只监控此时间之后的提交和MR (ISO格式: YYYY-MM-DDTHH:MM)
    
    # Webhook模式配置（独立）
    webhook_commits: bool = True  # Webhook是否响应Push事件
    webhook_mrs: bool = True      # Webhook是否响应MR事件
    webhook_branches: str = ""    # Webhook监控的分支（逗号分隔，空表示所有分支）
    
    # 轮询时间配置
    polling_interval: int = 5     # 轮询间隔（分钟）
    
    # 通用配置
    enable_comment: bool = True   # 是否启用评论回写
    
    # 状态信息
    last_commit_id: str = ""      # 上次检查的commit ID
    last_mr_id: int = 0           # 上次检查的MR ID
    last_check_time: str = ""     # 上次检查时间
    enabled: bool = True          # 是否启用
    clone_status: str = ""        # 克隆状态: "" / cloning / cloned / error
    
    # 触发模式配置
    trigger_mode: str = "polling" # 触发模式: polling / webhook / both
    webhook_secret: str = ""      # Webhook密钥（用于验证webhook请求）
    
    def to_dict(self):
        return asdict(self)
    
    def get_local_path(self) -> str:
        """获取本地存储路径"""
        if self.local_path:
            return self.local_path
        # 默认路径: /app/repos/{name}/{branch}
        return f"/app/repos/{self.name}/{self.branch}"
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PollingManager:
    """轮询任务管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._running = True  # 现在默认常驻运行
        self._thread: Optional[threading.Thread] = None
        self._repos: Dict[str, PollingRepo] = {}
        self._repos_lock = threading.RLock()
        self._review_callback: Optional[Callable] = None
        self._last_poll_times: Dict[str, float] = {}
        self._load_repos()
        
        # 自动启动后台线程
        self.start()
    
    def set_review_callback(self, callback: Callable):
        """设置审查回调函数"""
        self._review_callback = callback
    
    def _load_repos(self):
        """从数据库加载仓库配置"""
        repos_json = SettingsManager.get('polling_repos', '[]')
        try:
            repos_list = json.loads(repos_json)
            with self._repos_lock:
                self._repos = {r['id']: PollingRepo.from_dict(r) for r in repos_list}
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"加载仓库配置失败: {e}")
            with self._repos_lock:
                self._repos = {}
    
    def _save_repos(self):
        """保存仓库配置到数据库"""
        with self._repos_lock:
            repos_list = [r.to_dict() for r in self._repos.values()]
        SettingsManager.set('polling_repos', json.dumps(repos_list, ensure_ascii=False))
    
    def add_repo(self, repo: PollingRepo, verify: bool = False) -> bool:
        """
        添加仓库
        :param repo: 仓库配置对象
        :param verify: 是否在添加前验证连接
        """
        if verify:
            success, error = self.test_connectivity(repo)
            if not success:
                logger.error(f"验证仓库连接失败: {error}")
                return False

        with self._repos_lock:
            self._repos[repo.id] = repo
        self._save_repos()
        logger.info(f"添加轮询仓库: {repo.name} ({repo.url})")
        return True

    def test_connectivity(self, repo: PollingRepo) -> tuple[bool, str]:
        """
        测试仓库连通性
        :return: (是否成功, 错误信息)
        """
        import subprocess
        
        try:
            settings = SettingsManager.get_all()
            git_server_url = settings.get('git_server_url', '')
            
            auth_url = repo.url
            if repo.auth_type == 'http_basic' and repo.http_user and repo.http_password:
                auth_url = convert_to_http_auth_url(
                    repo.url,
                    http_user=repo.http_user,
                    http_password=repo.http_password,
                    server_url=git_server_url
                )
            elif repo.auth_type == 'token' and repo.token:
                auth_url = convert_to_http_auth_url(
                    repo.url,
                    token=repo.token,
                    server_url=git_server_url
                )
            
            # 使用 git ls-remote 验证连接
            cmd = ['git', 'ls-remote', '-h', auth_url, 'HEAD']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return True, ""
            else:
                return False, result.stderr or "未知错误"
                
        except subprocess.TimeoutExpired:
            return False, "连接超时 (15s)"
        except Exception as e:
            return False, str(e)
    
    def remove_repo(self, repo_id: str) -> bool:
        """删除仓库"""
        with self._repos_lock:
            if repo_id in self._repos:
                repo = self._repos.pop(repo_id)
                self._save_repos()
                logger.info(f"删除轮询仓库: {repo.name}")
                return True
        return False
    
    def update_repo(self, repo_id: str, updates: dict) -> bool:
        """更新仓库配置"""
        with self._repos_lock:
            if repo_id in self._repos:
                repo = self._repos[repo_id]
                for key, value in updates.items():
                    if hasattr(repo, key):
                        setattr(repo, key, value)
                self._save_repos()
                return True
        return False
    
    def get_repos(self) -> List[dict]:
        """获取所有仓库"""
        with self._repos_lock:
            return [r.to_dict() for r in self._repos.values()]
    
    def get_repo(self, repo_id: str) -> Optional[dict]:
        """获取单个仓库（字典格式）"""
        with self._repos_lock:
            if repo_id in self._repos:
                return self._repos[repo_id].to_dict()
        return None
    
    def get_repo_obj(self, repo_id: str) -> Optional[PollingRepo]:
        """获取单个仓库对象"""
        with self._repos_lock:
            return self._repos.get(repo_id)
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def start(self):
        """启动轮询（作为守护线程）"""
        if self._thread and self._thread.is_alive():
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()
        logger.info("轮询服务已启动（后台守护模式）")

    def stop(self):
        """停止轮询服务"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        logger.info("轮询服务已停止")
    
    
    def _polling_loop(self):
        """轮询主循环"""
        while self._running:
            try:
                # 获取全量仓库列表快照
                with self._repos_lock:
                    repos_snapshot = list(self._repos.values())
                
                now = time.time()
                
                # 检查所有启用的仓库
                for repo in repos_snapshot:
                    if not self._running:
                        break
                    
                    if not repo.enabled or repo.trigger_mode not in ['polling', 'both']:
                        continue
                    
                    # 检查是否到了该仓库的轮询时间
                    interval_seconds = repo.polling_interval * 60
                    last_poll = self._last_poll_times.get(repo.id, 0)
                    
                    if now - last_poll >= interval_seconds:
                        try:
                            logger.info(f"开始轮询仓库: {repo.name} (间隔: {repo.polling_interval}分)")
                            self._check_repo(repo)
                            self._last_poll_times[repo.id] = now
                        except Exception as e:
                            logger.error(f"检查仓库 {repo.name} 失败: {e}", exc_info=True)
                
                # 短暂休眠，避免空转消耗CPU
                for _ in range(10):  # 每10秒扫描一次任务列表
                    if not self._running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"轮询循环异常: {e}", exc_info=True)
                time.sleep(10)
    
    def _check_repo(self, repo: PollingRepo):
        """检查单个仓库的新提交/MR（使用git命令，不依赖API）"""
        
        # 解析生效时间
        effective_time = None
        if repo.effective_time:
            try:
                effective_time = datetime.fromisoformat(repo.effective_time.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"无效的生效时间格式: {repo.effective_time}")
        
        # 检查新提交 - 使用git ls-remote获取远程HEAD
        if repo.poll_commits:
            new_commits = self._get_new_commits_git(repo, effective_time)
            if new_commits:
                # 首次轮询（last_commit_id为空）只记录最新commit，不触发审查
                if not repo.last_commit_id:
                    logger.info(f"仓库 {repo.name} 首次轮询，记录最新commit: {new_commits[0]['id'][:8]}")
                    repo.last_commit_id = new_commits[0]['id']
                else:
                    logger.info(f"仓库 {repo.name} 发现 {len(new_commits)} 个新提交")
                    for commit in new_commits:
                        self._trigger_review(repo, 'commit', commit)
                    # 更新最后检查的commit
                    repo.last_commit_id = new_commits[0]['id']
        
        # 检查新MR - 使用git ls-remote检查MR refs
        if repo.poll_mrs:
            new_mrs = self._get_new_mrs_git(repo, effective_time)
            if new_mrs:
                # 首次轮询（last_mr_id为0）只记录最新MR ID，不触发审查
                if repo.last_mr_id == 0:
                    max_mr_id = max(mr['iid'] for mr in new_mrs)
                    logger.info(f"仓库 {repo.name} 首次轮询，记录最新MR ID: {max_mr_id}")
                    repo.last_mr_id = max_mr_id
                else:
                    logger.info(f"仓库 {repo.name} 发现 {len(new_mrs)} 个新MR")
                    for mr in new_mrs:
                        self._trigger_review(repo, 'merge_request', mr)
                    # 更新最后检查的MR
                    repo.last_mr_id = max(mr['iid'] for mr in new_mrs)
        
        # 更新检查时间
        repo.last_check_time = datetime.utcnow().isoformat()
        self._save_repos()
    
    def _get_new_commits_git(self, repo: PollingRepo, effective_time: Optional[datetime] = None) -> List[dict]:
        """使用git命令获取新提交（不依赖API）"""
        import subprocess
        
        try:
            # 构建认证URL
            settings = SettingsManager.get_all()
            git_server_url = settings.get('git_server_url', '')
            
            auth_url = repo.url
            if repo.auth_type == 'http_basic' and repo.http_user and repo.http_password:
                auth_url = convert_to_http_auth_url(
                    repo.url,
                    http_user=repo.http_user,
                    http_password=repo.http_password,
                    server_url=git_server_url
                )
            elif repo.auth_type == 'token' and repo.token:
                auth_url = convert_to_http_auth_url(
                    repo.url,
                    token=repo.token,
                    server_url=git_server_url
                )
            
            # 使用git ls-remote获取远程分支的最新commit SHA
            cmd = ['git', 'ls-remote', auth_url, f'refs/heads/{repo.branch}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"git ls-remote失败: {result.stderr}")
                return []
            
            # 解析输出: <sha>\trefs/heads/<branch>
            output = result.stdout.strip()
            if not output:
                logger.warning(f"仓库 {repo.name} 分支 {repo.branch} 未找到")
                return []
            
            remote_sha = output.split('\t')[0]
            
            # 如果和上次相同，没有新提交
            if remote_sha == repo.last_commit_id:
                return []
            
            # 发现新提交
            return [{
                'id': remote_sha,
                'message': f'New commit on {repo.branch}',
                'author': 'Polling',
            }]
            
        except subprocess.TimeoutExpired:
            logger.error(f"git ls-remote超时: {repo.name}")
            return []
        except Exception as e:
            logger.error(f"获取提交失败: {e}")
            return []
    
    def _get_new_mrs_git(self, repo: PollingRepo, effective_time: Optional[datetime] = None) -> List[dict]:
        """使用git命令获取新MR（通过检查refs/merge-requests或refs/pull）"""
        import subprocess
        
        try:
            # 构建认证URL
            settings = SettingsManager.get_all()
            git_server_url = settings.get('git_server_url', '')
            
            auth_url = repo.url
            if repo.auth_type == 'http_basic' and repo.http_user and repo.http_password:
                auth_url = convert_to_http_auth_url(
                    repo.url,
                    http_user=repo.http_user,
                    http_password=repo.http_password,
                    server_url=git_server_url
                )
            elif repo.auth_type == 'token' and repo.token:
                auth_url = convert_to_http_auth_url(
                    repo.url,
                    token=repo.token,
                    server_url=git_server_url
                )
            
            # 根据平台选择MR refs模式
            platform = repo.platform
            if platform == 'gitlab':
                # GitLab: refs/merge-requests/<id>/head
                ref_pattern = 'refs/merge-requests/*/head'
            else:
                # GitHub/Gitea: refs/pull/<id>/head
                ref_pattern = 'refs/pull/*/head'
            
            # 使用git ls-remote获取所有MR refs
            cmd = ['git', 'ls-remote', auth_url, ref_pattern]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                # 有些仓库可能不支持这种refs模式，静默处理
                logger.debug(f"git ls-remote MR失败: {result.stderr}")
                return []
            
            # 解析输出获取MR ID
            new_mrs = []
            for line in result.stdout.strip().split('\n'):
                if not line or '\t' not in line:
                    continue
                    
                sha, ref = line.split('\t')
                
                # 提取MR ID
                if platform == 'gitlab':
                    # refs/merge-requests/123/head -> 123
                    parts = ref.split('/')
                    if len(parts) >= 3:
                        try:
                            mr_id = int(parts[2])
                        except ValueError:
                            continue
                else:
                    # refs/pull/123/head -> 123
                    parts = ref.split('/')
                    if len(parts) >= 3:
                        try:
                            mr_id = int(parts[2])
                        except ValueError:
                            continue
                
                # 检查是否是新MR
                if mr_id > repo.last_mr_id:
                    new_mrs.append({
                        'iid': mr_id,
                        'title': f'MR #{mr_id}',
                        'source_branch': f'mr-{mr_id}',
                        'target_branch': repo.branch,
                        'source_ref': ref,  # 如 refs/merge-requests/123/head
                    })
            
            # 按ID排序（最新的在前）
            new_mrs.sort(key=lambda x: x['iid'], reverse=True)
            return new_mrs
            
        except subprocess.TimeoutExpired:
            logger.error(f"git ls-remote MR超时: {repo.name}")
            return []
        except Exception as e:
            logger.error(f"获取MR失败: {e}")
            return []
    
    
    def _trigger_review(self, repo: PollingRepo, strategy: str, item: dict):
        """触发代码审查"""
        if not self._review_callback:
            logger.warning("未设置审查回调函数")
            return
        
        # 使用仓库级别的配置
        platform = repo.platform
        project_path = extract_project_path(repo.url)
        
        # 从project_path解析owner和repo_name (格式: owner/repo 或 group/subgroup/repo)
        path_parts = project_path.split('/') if project_path else []
        repo_owner = path_parts[0] if len(path_parts) >= 2 else ''
        repo_name_parsed = path_parts[-1] if path_parts else repo.name
        
        # 使用仓库级别的认证信息，转换为认证URL用于克隆
        settings = SettingsManager.get_all()
        git_server_url = settings.get('git_server_url', '')
        
        clone_url = repo.url
        if repo.auth_type == 'http_basic' and repo.http_user and repo.http_password:
            clone_url = convert_to_http_auth_url(
                repo.url,
                http_user=repo.http_user,
                http_password=repo.http_password,
                server_url=git_server_url
            )
        elif repo.auth_type == 'token' and repo.token:
            clone_url = convert_to_http_auth_url(
                repo.url,
                token=repo.token,
                server_url=git_server_url
            )
        
        # 如果是纯轮询方式，不支持评论回写 (Requirement 3)
        enable_comment = repo.enable_comment
        if repo.trigger_mode == 'polling':
            if enable_comment:
                logger.info(f"仓库 {repo.name} 为纯轮询模式，已自动禁用评论回写")
            enable_comment = False

        context = {
            'strategy': strategy,
            'platform': platform,
            'project_id': project_path,
            'project_name': repo.name,
            'repo_owner': repo_owner,
            'repo_name': repo_name_parsed,
            'author_name': item.get('author', 'Polling'),
            'author_email': '',
            'local_path': repo.get_local_path(),  # 使用仓库配置的存储路径
            'enable_comment': enable_comment,  # 仓库级评论开关
            # 仓库级认证信息（用于评论回写）
            'repo_token': repo.token,
            'repo_http_user': repo.http_user,
            'repo_http_password': repo.http_password,
            'repo_api_url': repo.api_url,  # 仓库级API地址
            # 生效时间（用于过滤旧提交）
            'effective_time': repo.effective_time,
        }
        
        if strategy == 'commit':
            context['commit_id'] = item['id']
            logger.info(f"触发Commit审查: {repo.name} - {item['id'][:8]}")
        else:
            context['mr_iid'] = item['iid']
            context['pr_number'] = item['iid']  # Gitea/GitHub 使用 pr_number
            context['target_branch'] = item['target_branch']
            context['source_ref'] = item.get('source_ref', '')  # MR 源分支 ref
            logger.info(f"触发MR审查: {repo.name} - MR#{item['iid']}")

        
        try:
            # 使用已转换的HTTP认证URL调用审查
            self._review_callback(clone_url, repo.branch, strategy, context)
        except Exception as e:
            logger.error(f"触发审查失败: {e}")
    
    def get_status(self) -> dict:
        """获取轮询状态"""
        return {
            "repos_count": len(self._repos),
            "enabled_repos": sum(1 for r in self._repos.values() if r.enabled),
        }
    
    def clone_repo(self, repo: PollingRepo) -> dict:
        """克隆仓库到本地"""
        import subprocess
        import os
        
        local_path = repo.get_local_path()
        
        # 构建克隆URL
        settings = SettingsManager.get_all()
        git_server_url = settings.get('git_server_url', '')
        
        clone_url = repo.url
        if repo.auth_type == 'http_basic' and repo.http_user and repo.http_password:
            clone_url = convert_to_http_auth_url(
                repo.url,
                repo.http_user,
                repo.http_password,
                git_server_url
            )
        
        try:
            # 更新状态
            repo.clone_status = 'cloning'
            self._save_repos()
            
            # 如果目录已存在，先删除
            if os.path.exists(local_path):
                import shutil
                shutil.rmtree(local_path)
            
            # 创建父目录
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 执行克隆
            cmd = ['git', 'clone', '--branch', repo.branch, '--single-branch', clone_url, local_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                repo.clone_status = 'cloned'
                self._save_repos()
                logger.info(f"仓库 {repo.name} 克隆成功: {local_path}")
                return {"success": True, "message": f"克隆成功: {local_path}", "path": local_path}
            else:
                repo.clone_status = 'error'
                self._save_repos()
                logger.error(f"仓库 {repo.name} 克隆失败: {result.stderr}")
                return {"success": False, "message": f"克隆失败: {result.stderr[:200]}"}
                
        except subprocess.TimeoutExpired:
            repo.clone_status = 'error'
            self._save_repos()
            return {"success": False, "message": "克隆超时"}
        except Exception as e:
            repo.clone_status = 'error'
            self._save_repos()
            logger.error(f"克隆仓库失败: {e}")
            return {"success": False, "message": str(e)}
    
    def get_branches(self, repo_url: str, platform: str, auth_type: str, 
                     token: str = '', http_user: str = '', http_password: str = '',
                     api_url: str = '') -> list:
        """使用git ls-remote获取仓库分支列表"""
        import subprocess
        
        try:
            # 构建认证URL
            settings = SettingsManager.get_all()
            git_server_url = settings.get('git_server_url', '')
            
            auth_url = repo_url
            if auth_type == 'http_basic' and http_user and http_password:
                auth_url = convert_to_http_auth_url(
                    repo_url,
                    http_user=http_user,
                    http_password=http_password,
                    server_url=git_server_url
                )
            elif auth_type == 'token' and token:
                auth_url = convert_to_http_auth_url(
                    repo_url,
                    token=token,
                    server_url=git_server_url
                )
            
            # 执行git ls-remote获取分支
            cmd = ['git', 'ls-remote', '--heads', auth_url]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"git ls-remote失败: {result.stderr}")
                return []
            
            # 解析输出: <sha>\trefs/heads/<branch_name>
            branches = []
            for line in result.stdout.strip().split('\n'):
                if line and '\t' in line:
                    ref = line.split('\t')[1]
                    if ref.startswith('refs/heads/'):
                        branch_name = ref.replace('refs/heads/', '')
                        branches.append(branch_name)
            
            logger.info(f"获取到 {len(branches)} 个分支")
            return branches
            
        except subprocess.TimeoutExpired:
            logger.error("git ls-remote超时")
            return []
        except Exception as e:
            logger.error(f"获取分支列表失败: {e}")
            return []


# 全局实例
polling_manager = PollingManager()
