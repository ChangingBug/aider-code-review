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
from utils import logger, convert_to_http_auth_url


@dataclass
class PollingRepo:
    """轮询仓库配置"""
    id: str
    name: str
    url: str                    # 仓库URL (HTTP格式)
    branch: str = "main"        # 监控的分支
    strategy: str = "commit"    # 审查策略: commit / mr
    poll_commits: bool = True   # 是否轮询新提交
    poll_mrs: bool = False      # 是否轮询新MR
    last_commit_id: str = ""    # 上次检查的commit ID
    last_mr_id: int = 0         # 上次检查的MR ID
    last_check_time: str = ""   # 上次检查时间
    enabled: bool = True        # 是否启用
    
    def to_dict(self):
        return asdict(self)
    
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
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._repos: Dict[str, PollingRepo] = {}
        self._review_callback: Optional[Callable] = None
        self._load_repos()
    
    def set_review_callback(self, callback: Callable):
        """设置审查回调函数"""
        self._review_callback = callback
    
    def _load_repos(self):
        """从数据库加载仓库配置"""
        repos_json = SettingsManager.get('polling_repos', '[]')
        try:
            repos_list = json.loads(repos_json)
            self._repos = {r['id']: PollingRepo.from_dict(r) for r in repos_list}
        except (json.JSONDecodeError, KeyError):
            self._repos = {}
    
    def _save_repos(self):
        """保存仓库配置到数据库"""
        repos_list = [r.to_dict() for r in self._repos.values()]
        SettingsManager.set('polling_repos', json.dumps(repos_list, ensure_ascii=False))
    
    def add_repo(self, repo: PollingRepo) -> bool:
        """添加仓库"""
        self._repos[repo.id] = repo
        self._save_repos()
        logger.info(f"添加轮询仓库: {repo.name} ({repo.url})")
        return True
    
    def remove_repo(self, repo_id: str) -> bool:
        """删除仓库"""
        if repo_id in self._repos:
            repo = self._repos.pop(repo_id)
            self._save_repos()
            logger.info(f"删除轮询仓库: {repo.name}")
            return True
        return False
    
    def update_repo(self, repo_id: str, updates: dict) -> bool:
        """更新仓库配置"""
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
        return [r.to_dict() for r in self._repos.values()]
    
    def get_repo(self, repo_id: str) -> Optional[dict]:
        """获取单个仓库"""
        if repo_id in self._repos:
            return self._repos[repo_id].to_dict()
        return None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def start(self):
        """启动轮询"""
        if self._running:
            logger.warning("轮询已在运行中")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()
        logger.info("轮询任务已启动")
    
    def stop(self):
        """停止轮询"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("轮询任务已停止")
    
    def _polling_loop(self):
        """轮询主循环"""
        while self._running:
            try:
                interval = SettingsManager.get_int('polling_interval', 5)
                
                # 检查所有启用的仓库
                for repo_id, repo in list(self._repos.items()):
                    if not self._running:
                        break
                    if not repo.enabled:
                        continue
                    
                    try:
                        self._check_repo(repo)
                    except Exception as e:
                        logger.error(f"检查仓库 {repo.name} 失败: {e}")
                
                # 等待下一次轮询
                for _ in range(interval * 60):
                    if not self._running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"轮询循环异常: {e}")
                time.sleep(10)
    
    def _check_repo(self, repo: PollingRepo):
        """检查单个仓库的新提交/MR"""
        settings = SettingsManager.get_all()
        platform = settings.get('git_platform', 'gitlab')
        api_url = settings.get('git_api_url', '')
        token = settings.get('git_token', '')
        
        # 获取HTTP认证信息（作为API Token的备选）
        http_user = settings.get('git_http_user', '')
        http_password = settings.get('git_http_password', '')
        
        if not api_url:
            logger.warning(f"Git API地址未配置，跳过仓库 {repo.name}")
            return
        
        # 构建认证信息：优先使用Token，否则使用HTTP Basic认证
        auth_info = self._build_auth_info(platform, token, http_user, http_password)
        
        # 从URL提取项目路径
        project_path = self._extract_project_path(repo.url, platform)
        if not project_path:
            logger.warning(f"无法解析仓库路径: {repo.url}")
            return
        
        # 检查新提交
        if repo.poll_commits:
            new_commits = self._get_new_commits(platform, api_url, auth_info, project_path, repo.branch, repo.last_commit_id)
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
        
        # 检查新MR
        if repo.poll_mrs:
            new_mrs = self._get_new_mrs(platform, api_url, auth_info, project_path, repo.last_mr_id)
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
    
    def _build_auth_info(self, platform: str, token: str, http_user: str, http_password: str) -> dict:
        """
        构建认证信息
        优先使用API Token，如果没有则使用HTTP Basic认证
        返回: {"headers": {...}, "auth": (user, pass) or None}
        """
        headers = {}
        auth = None
        
        if token:
            # 使用API Token认证
            if platform == 'gitlab':
                headers["PRIVATE-TOKEN"] = token
            elif platform == 'gitea':
                headers["Authorization"] = f"token {token}"
            elif platform == 'github':
                headers["Authorization"] = f"token {token}"
                headers["Accept"] = "application/vnd.github.v3+json"
        elif http_user and http_password:
            # 使用HTTP Basic认证
            auth = (http_user, http_password)
            logger.debug(f"使用HTTP Basic认证 (用户: {http_user})")
        else:
            logger.warning("未配置认证信息 (API Token 或 HTTP用户名/密码)")
        
        return {"headers": headers, "auth": auth}
    
    def _extract_project_path(self, url: str, platform: str) -> Optional[str]:
        """从URL提取项目路径"""
        # SSH格式: git@host:group/project.git
        ssh_match = re.match(r'git@[^:]+:(.+?)(?:\.git)?$', url)
        if ssh_match:
            return ssh_match.group(1)
        
        # HTTP格式: http(s)://host/group/project.git
        http_match = re.match(r'https?://[^/]+/(.+?)(?:\.git)?$', url)
        if http_match:
            return http_match.group(1)
        
        return None
    
    def _get_new_commits(self, platform: str, api_url: str, auth_info: dict, 
                         project_path: str, branch: str, last_commit_id: str) -> List[dict]:
        """获取新提交"""
        try:
            from urllib.parse import quote
            encoded_path = quote(project_path, safe='')
            
            if platform == 'gitlab':
                url = f"{api_url}/projects/{encoded_path}/repository/commits"
                params = {"ref_name": branch, "per_page": 10}
            elif platform == 'gitea':
                url = f"{api_url}/repos/{project_path}/commits"
                params = {"sha": branch, "limit": 10}
            elif platform == 'github':
                url = f"{api_url}/repos/{project_path}/commits"
                params = {"sha": branch, "per_page": 10}
            else:
                return []
            
            response = requests.get(
                url, 
                headers=auth_info.get('headers', {}),
                auth=auth_info.get('auth'),
                params=params, 
                timeout=30
            )
            response.raise_for_status()
            commits = response.json()
            
            # 过滤出新提交
            new_commits = []
            for commit in commits:
                commit_id = commit.get('id') or commit.get('sha')
                if commit_id == last_commit_id:
                    break
                new_commits.append({
                    'id': commit_id,
                    'message': commit.get('message') or commit.get('commit', {}).get('message', ''),
                    'author': commit.get('author_name') or commit.get('commit', {}).get('author', {}).get('name', ''),
                })
            
            return new_commits
            
        except Exception as e:
            logger.error(f"获取提交列表失败: {e}")
            return []
    
    def _get_new_mrs(self, platform: str, api_url: str, auth_info: dict,
                     project_path: str, last_mr_id: int) -> List[dict]:
        """获取新MR"""
        try:
            from urllib.parse import quote
            encoded_path = quote(project_path, safe='')
            
            if platform == 'gitlab':
                url = f"{api_url}/projects/{encoded_path}/merge_requests"
                params = {"state": "opened", "per_page": 10}
            elif platform == 'gitea':
                url = f"{api_url}/repos/{project_path}/pulls"
                params = {"state": "open", "limit": 10}
            elif platform == 'github':
                url = f"{api_url}/repos/{project_path}/pulls"
                params = {"state": "open", "per_page": 10}
            else:
                return []
            
            response = requests.get(
                url, 
                headers=auth_info.get('headers', {}),
                auth=auth_info.get('auth'),
                params=params, 
                timeout=30
            )
            response.raise_for_status()
            mrs = response.json()
            
            # 过滤出新MR
            new_mrs = []
            for mr in mrs:
                mr_iid = mr.get('iid') or mr.get('number')
                if mr_iid and mr_iid > last_mr_id:
                    new_mrs.append({
                        'iid': mr_iid,
                        'title': mr.get('title', ''),
                        'source_branch': mr.get('source_branch') or mr.get('head', {}).get('ref', ''),
                        'target_branch': mr.get('target_branch') or mr.get('base', {}).get('ref', ''),
                    })
            
            return new_mrs
            
        except Exception as e:
            logger.error(f"获取MR列表失败: {e}")
            return []
    
    def _trigger_review(self, repo: PollingRepo, strategy: str, item: dict):
        """触发代码审查"""
        if not self._review_callback:
            logger.warning("未设置审查回调函数")
            return
        
        settings = SettingsManager.get_all()
        platform = settings.get('git_platform', 'gitlab')
        project_path = self._extract_project_path(repo.url, platform)
        
        # 从project_path解析owner和repo_name (格式: owner/repo 或 group/subgroup/repo)
        path_parts = project_path.split('/') if project_path else []
        repo_owner = path_parts[0] if len(path_parts) >= 2 else ''
        repo_name_parsed = path_parts[-1] if path_parts else repo.name
        
        # 获取HTTP认证信息，转换为认证URL用于克隆
        git_http_user = settings.get('git_http_user', '')
        git_http_password = settings.get('git_http_password', '')
        git_server_url = settings.get('git_server_url', '')
        
        # 将仓库URL转换为带HTTP认证的URL
        clone_url = repo.url
        if git_http_user and git_http_password:
            clone_url = convert_to_http_auth_url(
                repo.url,
                git_http_user,
                git_http_password,
                git_server_url
            )
            logger.debug(f"已转换为HTTP认证URL")
        
        context = {
            'strategy': strategy,
            'platform': platform,
            'project_id': project_path,
            'project_name': repo.name,
            'repo_owner': repo_owner,
            'repo_name': repo_name_parsed,
            'author_name': item.get('author', 'Polling'),
            'author_email': '',
        }
        
        if strategy == 'commit':
            context['commit_id'] = item['id']
            logger.info(f"触发Commit审查: {repo.name} - {item['id'][:8]}")
        else:
            context['mr_iid'] = item['iid']
            context['pr_number'] = item['iid']  # Gitea/GitHub 使用 pr_number
            context['target_branch'] = item['target_branch']
            logger.info(f"触发MR审查: {repo.name} - MR#{item['iid']}")
        
        try:
            # 使用已转换的HTTP认证URL调用审查
            self._review_callback(clone_url, repo.branch, strategy, context)
        except Exception as e:
            logger.error(f"触发审查失败: {e}")
    
    def get_status(self) -> dict:
        """获取轮询状态"""
        return {
            "running": self._running,
            "repos_count": len(self._repos),
            "enabled_repos": sum(1 for r in self._repos.values() if r.enabled),
            "interval": SettingsManager.get_int('polling_interval', 5),
        }


# 全局实例
polling_manager = PollingManager()
