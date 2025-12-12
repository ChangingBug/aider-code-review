#!/usr/bin/env python3
"""
Webhook 测试脚本
模拟 Git 平台发送 Webhook 事件触发代码审查

使用方法:
    python scripts/test_webhook.py --platform gitlab --event push --server http://localhost:5000
    python scripts/test_webhook.py --platform gitea --event mr --server http://localhost:5000
"""

import argparse
import json
import requests
from datetime import datetime


def generate_gitlab_push_payload():
    """生成 GitLab Push 事件 payload"""
    return {
        "object_kind": "push",
        "event_name": "push",
        "ref": "refs/heads/main",
        "checkout_sha": "abc123def456",
        "user_name": "Test User",
        "user_email": "test@example.com",
        "project_id": 1,
        "project": {
            "id": 1,
            "name": "test-project",
            "ssh_url": "git@code.example.com:group/test-project.git",
            "http_url": "http://code.example.com/group/test-project.git"
        },
        "commits": [
            {
                "id": "abc123def456789012345678901234567890abcd",
                "message": "Test commit for webhook testing",
                "author": {
                    "name": "Test User",
                    "email": "test@example.com"
                },
                "added": ["new_file.py"],
                "modified": ["existing_file.py"],
                "removed": []
            }
        ],
        "total_commits_count": 1
    }


def generate_gitlab_mr_payload():
    """生成 GitLab Merge Request 事件 payload"""
    return {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "user": {
            "name": "Test User",
            "username": "testuser",
            "email": "test@example.com"
        },
        "project": {
            "id": 1,
            "name": "test-project",
            "ssh_url": "git@code.example.com:group/test-project.git"
        },
        "object_attributes": {
            "iid": 42,
            "title": "Test Merge Request",
            "source_branch": "feature-branch",
            "target_branch": "main",
            "state": "opened",
            "action": "open"
        }
    }


def generate_gitea_push_payload():
    """生成 Gitea Push 事件 payload"""
    return {
        "ref": "refs/heads/main",
        "repository": {
            "id": 1,
            "name": "test-project",
            "full_name": "group/test-project",
            "ssh_url": "git@code.example.com:group/test-project.git",
            "clone_url": "http://code.example.com/group/test-project.git",
            "owner": {
                "username": "group"
            }
        },
        "pusher": {
            "username": "testuser",
            "email": "test@example.com"
        },
        "sender": {
            "username": "testuser",
            "email": "test@example.com"
        },
        "commits": [
            {
                "id": "abc123def456789012345678901234567890abcd",
                "message": "Test commit for webhook testing",
                "author": {
                    "name": "Test User",
                    "email": "test@example.com"
                }
            }
        ]
    }


def generate_gitea_pr_payload():
    """生成 Gitea Pull Request 事件 payload"""
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "id": 42,
            "number": 42,
            "title": "Test Pull Request",
            "head": {
                "ref": "feature-branch"
            },
            "base": {
                "ref": "main"
            }
        },
        "repository": {
            "id": 1,
            "name": "test-project",
            "full_name": "group/test-project",
            "ssh_url": "git@code.example.com:group/test-project.git",
            "owner": {
                "username": "group"
            }
        },
        "sender": {
            "username": "testuser",
            "email": "test@example.com"
        }
    }


def generate_github_push_payload():
    """生成 GitHub Push 事件 payload"""
    return {
        "ref": "refs/heads/main",
        "repository": {
            "id": 1,
            "name": "test-project",
            "full_name": "group/test-project",
            "ssh_url": "git@github.com:group/test-project.git",
            "clone_url": "https://github.com/group/test-project.git",
            "owner": {
                "login": "group"
            }
        },
        "pusher": {
            "name": "testuser",
            "email": "test@example.com"
        },
        "sender": {
            "login": "testuser"
        },
        "commits": [
            {
                "id": "abc123def456789012345678901234567890abcd",
                "message": "Test commit for webhook testing",
                "author": {
                    "name": "Test User",
                    "email": "test@example.com"
                }
            }
        ]
    }


def generate_github_pr_payload():
    """生成 GitHub Pull Request 事件 payload"""
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "id": 42,
            "number": 42,
            "title": "Test Pull Request",
            "head": {
                "ref": "feature-branch"
            },
            "base": {
                "ref": "main"
            },
            "user": {
                "login": "testuser"
            }
        },
        "repository": {
            "id": 1,
            "name": "test-project",
            "full_name": "group/test-project",
            "ssh_url": "git@github.com:group/test-project.git",
            "owner": {
                "login": "group"
            }
        },
        "sender": {
            "login": "testuser"
        }
    }


def send_webhook(server_url: str, platform: str, event_type: str, payload: dict):
    """发送 Webhook 请求"""
    url = f"{server_url.rstrip('/')}/webhook"
    
    # 根据平台设置 Header
    headers = {"Content-Type": "application/json"}
    
    if platform == "gitlab":
        if event_type == "push":
            headers["X-Gitlab-Event"] = "Push Hook"
        else:
            headers["X-Gitlab-Event"] = "Merge Request Hook"
    elif platform == "gitea":
        if event_type == "push":
            headers["X-Gitea-Event"] = "push"
        else:
            headers["X-Gitea-Event"] = "pull_request"
    elif platform == "github":
        if event_type == "push":
            headers["X-GitHub-Event"] = "push"
        else:
            headers["X-GitHub-Event"] = "pull_request"
    
    print(f"\n{'='*50}")
    print(f"发送 {platform.upper()} {event_type.upper()} Webhook")
    print(f"{'='*50}")
    print(f"URL: {url}")
    print(f"Headers: {json.dumps(headers, indent=2)}")
    print(f"Payload: {json.dumps(payload, indent=2)[:500]}...")
    print()
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        
        if response.status_code == 200:
            print("\n✅ Webhook 发送成功！")
        else:
            print(f"\n⚠️ 返回状态码: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 无法连接到服务器: {url}")
        print("请确保服务已启动")
    except Exception as e:
        print(f"\n❌ 发送失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="Webhook 测试脚本")
    parser.add_argument(
        "--platform", "-p",
        choices=["gitlab", "gitea", "github"],
        default="gitlab",
        help="Git 平台类型 (默认: gitlab)"
    )
    parser.add_argument(
        "--event", "-e",
        choices=["push", "mr"],
        default="push",
        help="事件类型: push 或 mr (默认: push)"
    )
    parser.add_argument(
        "--server", "-s",
        default="http://localhost:5000",
        help="服务器地址 (默认: http://localhost:5000)"
    )
    
    args = parser.parse_args()
    
    # 生成 payload
    payload_generators = {
        ("gitlab", "push"): generate_gitlab_push_payload,
        ("gitlab", "mr"): generate_gitlab_mr_payload,
        ("gitea", "push"): generate_gitea_push_payload,
        ("gitea", "mr"): generate_gitea_pr_payload,
        ("github", "push"): generate_github_push_payload,
        ("github", "mr"): generate_github_pr_payload,
    }
    
    generator = payload_generators.get((args.platform, args.event))
    if not generator:
        print(f"不支持的组合: {args.platform} + {args.event}")
        return
    
    payload = generator()
    send_webhook(args.server, args.platform, args.event, payload)


if __name__ == "__main__":
    main()
