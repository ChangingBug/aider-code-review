"""
Git 评论回写服务
"""
import requests
from urllib.parse import quote

from settings import SettingsManager
from utils import logger, build_git_auth


def post_comment_to_git(context: dict, report: str):
    """回写评论到Git平台"""
    platform = context.get('platform', 'gitlab')
    
    # 优先使用仓库级认证信息和API地址
    settings = SettingsManager.get_all()
    token = context.get('repo_token', '') or settings.get('git_token', '')
    http_user = context.get('repo_http_user', '') or settings.get('git_http_user', '')
    http_password = context.get('repo_http_password', '') or settings.get('git_http_password', '')
    api_url = context.get('repo_api_url', '') or settings.get('git_api_url', '')
    
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
