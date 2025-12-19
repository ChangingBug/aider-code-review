"""
单元测试模块
测试核心功能的正确性
"""
import pytest
import json
import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    parse_aider_output,
    filter_valid_files,
    format_review_comment,
    sanitize_branch_name,
    convert_to_http_auth_url,
    build_git_auth
)


class TestParseAiderOutput:
    """测试Aider输出解析"""
    
    def test_empty_output(self):
        """空输出应返回警告信息"""
        result = parse_aider_output("")
        assert "未获取到审查结果" in result
    
    def test_none_output(self):
        """None输出应返回警告信息"""
        result = parse_aider_output(None)
        assert "未获取到审查结果" in result
    
    def test_markdown_extraction(self):
        """应正确提取Markdown内容"""
        raw = """
Tokens: 1234
Model: qwen-2.5-coder
───────────────────────
# 代码审查报告

## 问题列表
- 问题1
- 问题2
"""
        result = parse_aider_output(raw)
        assert "# 代码审查报告" in result
        assert "问题1" in result
        assert "Tokens:" not in result


class TestFilterValidFiles:
    """测试文件过滤功能"""
    
    def test_valid_extensions(self):
        """应保留有效扩展名的文件"""
        files = ['main.py', 'app.js', 'style.css', 'readme.txt']
        valid_ext = ['.py', '.js']
        result = filter_valid_files(files, valid_ext)
        assert 'main.py' in result
        assert 'app.js' in result
        assert 'style.css' not in result
    
    def test_exclude_node_modules(self):
        """应排除node_modules目录"""
        files = ['src/main.py', 'node_modules/lodash/index.js']
        result = filter_valid_files(files, ['.py', '.js'])
        assert 'src/main.py' in result
        assert 'node_modules/lodash/index.js' not in result
    
    def test_exclude_vendor(self):
        """应排除vendor目录"""
        files = ['src/main.py', 'vendor/lib/helper.py']
        result = filter_valid_files(files, ['.py'])
        assert 'src/main.py' in result
        assert 'vendor/lib/helper.py' not in result
    
    def test_exclude_minified(self):
        """应排除压缩文件"""
        files = ['app.js', 'app.min.js', 'vendor.bundle.js']
        result = filter_valid_files(files, ['.js'])
        assert 'app.js' in result
        assert 'app.min.js' not in result


class TestSanitizeBranchName:
    """测试分支名处理"""
    
    def test_refs_heads(self):
        """应移除refs/heads/前缀"""
        assert sanitize_branch_name("refs/heads/main") == "main"
        assert sanitize_branch_name("refs/heads/feature/test") == "feature/test"
    
    def test_plain_branch(self):
        """普通分支名应保持不变"""
        assert sanitize_branch_name("main") == "main"
        assert sanitize_branch_name("develop") == "develop"


class TestConvertToHttpAuthUrl:
    """测试URL转换"""
    
    def test_http_url_with_auth(self):
        """HTTP URL应正确添加认证信息"""
        result = convert_to_http_auth_url(
            "http://gitlab.com/group/project.git",
            "user", "pass"
        )
        assert "user:pass@" in result
        assert "http://" in result
    
    def test_ssh_url_conversion(self):
        """SSH URL应转换为HTTP格式"""
        result = convert_to_http_auth_url(
            "git@gitlab.com:group/project.git",
            "user", "pass",
            "http://gitlab.com"
        )
        assert "http://" in result
        assert "git@" not in result


class TestBuildGitAuth:
    """测试Git认证信息构建"""
    
    def test_token_auth_gitlab(self):
        """GitLab Token认证"""
        result = build_git_auth("gitlab", token="test-token")
        assert result["headers"]["PRIVATE-TOKEN"] == "test-token"
    
    def test_token_auth_github(self):
        """GitHub Token认证"""
        result = build_git_auth("github", token="test-token")
        assert "Authorization" in result["headers"]
        assert "Bearer" in result["headers"]["Authorization"]
    
    def test_http_basic_auth(self):
        """HTTP Basic认证"""
        result = build_git_auth("gitlab", http_user="user", http_password="pass")
        assert result["auth"] == ("user", "pass")
    
    def test_no_auth(self):
        """无认证信息"""
        result = build_git_auth("gitlab")
        assert result["auth"] is None


class TestPollingRepo:
    """测试轮询仓库配置"""
    
    def test_polling_repo_creation(self):
        """测试PollingRepo创建"""
        from polling import PollingRepo
        
        repo = PollingRepo(
            id="test-id",
            name="test-repo",
            url="http://gitlab.com/test/repo.git"
        )
        assert repo.id == "test-id"
        assert repo.name == "test-repo"
        assert repo.branch == "main"  # 默认值
        assert repo.trigger_mode == "polling"  # 默认值
    
    def test_polling_repo_to_dict(self):
        """测试PollingRepo序列化"""
        from polling import PollingRepo
        
        repo = PollingRepo(
            id="test-id",
            name="test-repo",
            url="http://gitlab.com/test/repo.git"
        )
        data = repo.to_dict()
        assert data["id"] == "test-id"
        assert data["name"] == "test-repo"
    
    def test_polling_repo_from_dict(self):
        """测试PollingRepo反序列化"""
        from polling import PollingRepo
        
        data = {
            "id": "test-id",
            "name": "test-repo",
            "url": "http://gitlab.com/test/repo.git",
            "branch": "develop"
        }
        repo = PollingRepo.from_dict(data)
        assert repo.id == "test-id"
        assert repo.branch == "develop"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
