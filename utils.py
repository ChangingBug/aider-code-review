"""
工具函数模块
"""
import logging
import re
from typing import List, Optional

# 配置日志 - 仅配置本模块logger，避免影响其他模块
logger = logging.getLogger("aider-reviewer")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def parse_aider_output(raw_output: str) -> str:
    """
    清洗Aider输出，提取有效的审查报告
    
    Aider输出通常包含：
    - Token统计信息
    - 模型交互日志
    - 实际的回复内容
    
    我们需要提取最后的Markdown格式回复
    """
    if not raw_output:
        return "⚠️ 未获取到审查结果"
    
    lines = raw_output.split('\n')
    result_lines = []
    in_response = False
    
    for line in lines:
        # 跳过Aider的系统日志行
        if any(skip in line for skip in [
            'Tokens:', 'Cost:', 'Model:', 'Git repo:', 
            'Repo-map:', 'Added', 'Removed', '───',
            'Aider v', 'Main model:', 'Weak model:'
        ]):
            continue
        
        # 检测到Markdown格式内容开始
        if line.startswith('#') or line.startswith('- ') or line.startswith('* '):
            in_response = True
        
        if in_response or line.strip():
            result_lines.append(line)
    
    # 如果解析失败，返回最后4000字符作为fallback
    result = '\n'.join(result_lines).strip()
    if not result:
        result = raw_output[-4000:]
    
    return result


def filter_valid_files(files: List[str], valid_extensions: List[str]) -> List[str]:
    """
    过滤有效的代码文件
    排除第三方库、node_modules、vendor等目录
    """
    # 排除的目录模式
    EXCLUDED_DIRS = [
        'node_modules/', 'vendor/', 'lib/', 'libs/', 'plugins/',
        '.git/', '.svn/', 'dist/', 'build/', 'target/',
        '__pycache__/', '.cache/', '.vscode/', '.idea/',
        'static/platform/', 'static/lib/', 'static/vendor/',
    ]
    
    # 排除的文件模式
    EXCLUDED_FILES = [
        '.min.js', '.min.css', '.bundle.js', '.chunk.js',
        'jquery', 'bootstrap', 'vue.js', 'react.', 'angular.',
        'lodash', 'moment', 'axios', 'echarts',
        '.map', '.lock', 'package-lock.json', 'yarn.lock',
    ]
    
    result = []
    for f in files:
        # 检查扩展名
        if not any(f.endswith(ext) for ext in valid_extensions):
            continue
        
        # 检查排除目录
        f_lower = f.lower()
        if any(excl in f_lower for excl in EXCLUDED_DIRS):
            logger.debug(f"排除库目录文件: {f}")
            continue
        
        # 检查排除文件模式
        if any(excl in f_lower for excl in EXCLUDED_FILES):
            logger.debug(f"排除库文件: {f}")
            continue
        
        result.append(f)
    
    return result


def format_review_comment(report: str, strategy: str, context: dict) -> str:
    """
    格式化审查报告为Git评论格式
    """
    header = "## 🤖 AI代码审查报告\n\n"
    
    if strategy == "commit":
        header += f"**审查类型**: Commit审查\n"
        header += f"**Commit ID**: `{context.get('commit_id', 'N/A')}`\n\n"
    elif strategy == "merge_request":
        header += f"**审查类型**: Merge Request审查\n"
        header += f"**目标分支**: `{context.get('target_branch', 'N/A')}`\n\n"
    
    header += "---\n\n"
    
    return header + report


def get_commit_prompt() -> str:
    """获取Commit审查的Prompt模板"""
    return """请审查这个Commit的代码变更，并生成结构化的审查报告。

# 输出格式（严格按照以下结构）

## 📊 评审结论

| 维度 | 评分 | 说明 |
|------|------|------|
| 代码质量 | ⭐⭐⭐⭐☆ | 简要说明 |
| 安全性 | ⭐⭐⭐⭐⭐ | 简要说明 |
| 可维护性 | ⭐⭐⭐☆☆ | 简要说明 |
| 总体评价 | **通过/待改进/不通过** | 总结 |

## 🔴 严重问题

### 问题1：[问题标题]
- **文件**: `path/to/file.java:行号`
- **描述**: 详细说明问题
- **风险**: 可能导致的后果
- **建议修复**:
```java
// 修改前
旧代码

// 修改后
新代码
```

## 🟡 警告

### 问题1：[问题标题]
- **文件**: `path/to/file.java:行号`
- **描述**: 详细说明
- **建议**: 改进方案

## 🔵 优化建议

- 建议1：描述
- 建议2：描述

## ✅ 亮点

- 代码中做得好的地方

---

# 审查要点

1. **逻辑错误**: 空指针、边界条件、并发问题
2. **安全漏洞**: SQL注入、XSS、敏感信息泄露、权限校验
3. **代码规范**: 命名、注释、代码结构
4. **性能问题**: 循环效率、资源泄漏、缓存使用

⚠️ 重要：不要输出任何代码编辑块，只提供文字审查报告。如需展示代码对比，使用markdown代码块。"""


def get_mr_prompt(target_branch: str) -> str:
    """获取Merge Request审查的Prompt模板"""
    return f"""这是一个合并请求(Merge Request)，目标分支: {target_branch}

请对当前分支相对于目标分支的所有变更进行全面审查，并生成结构化的审查报告。

# 输出格式（严格按照以下结构）

## 📋 MR概要

| 项目 | 内容 |
|------|------|
| 目标分支 | {target_branch} |
| 变更范围 | 简述本次MR的主要变更 |
| 影响评估 | 低/中/高 |

## 📊 评审结论

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构影响 | ⭐⭐⭐⭐☆ | 对整体架构的影响程度 |
| API兼容性 | ⭐⭐⭐⭐⭐ | 是否有Breaking Changes |
| 代码质量 | ⭐⭐⭐☆☆ | 可读性、可维护性 |
| 测试覆盖 | ⭐⭐⭐⭐☆ | 测试是否充分 |
| 安全性 | ⭐⭐⭐⭐⭐ | 安全风险评估 |
| **总体评价** | **可合并/需修改/拒绝** | 总结建议 |

## 🔴 严重问题（必须修复）

### 问题1：[问题标题]
- **文件**: `path/to/file.java:行号`
- **描述**: 详细说明问题
- **风险**: 可能导致的后果
- **建议修复**:
```java
// 修改前
旧代码

// 修改后
新代码
```

## 🟡 警告（建议修复）

### 问题1：[问题标题]
- **文件**: `path/to/file.java:行号`
- **描述**: 详细说明
- **建议**: 改进方案

## 🔵 优化建议（可选）

- 建议1：描述
- 建议2：描述

## ✅ 亮点

- 本次MR做得好的地方

---

# 审查要点

1. **架构影响**: 评估变更对整体架构的影响
2. **API兼容性**: 检查是否有Breaking Changes
3. **代码质量**: 代码可读性、可维护性、测试覆盖
4. **安全性**: 潜在的安全风险
5. **性能**: 可能的性能瓶颈

⚠️ 重要：不要输出任何代码编辑块，只提供文字审查报告。如需展示代码对比，使用markdown代码块。"""


def sanitize_branch_name(ref: str) -> str:
    """从Git ref中提取分支名"""
    return ref.replace('refs/heads/', '').replace('refs/tags/', '')


def convert_to_http_auth_url(repo_url: str, http_user: str, http_password: str, server_url: str = "") -> str:
    """
    将Git仓库URL转换为带HTTP认证的URL
    
    支持以下输入格式：
    - SSH: git@code.example.com:group/project.git
    - HTTP: http://code.example.com/group/project.git
    - HTTPS: https://code.example.com/group/project.git
    
    输出格式：
    - http://用户名:密码@code.example.com/group/project.git
    
    Args:
        repo_url: 原始仓库URL
        http_user: HTTP认证用户名
        http_password: HTTP认证密码
        server_url: Git服务器基础URL（可选，用于覆盖解析出的服务器地址）
    
    Returns:
        带认证信息的HTTP URL
    """
    from urllib.parse import quote
    
    if not http_user or not http_password:
        logger.warning("未配置HTTP认证信息，使用原始URL")
        return repo_url
    
    # URL编码密码中的特殊字符
    encoded_password = quote(http_password, safe='')
    encoded_user = quote(http_user, safe='')
    
    # 解析SSH URL: git@host:path.git
    ssh_pattern = r'^git@([^:]+):(.+)$'
    ssh_match = re.match(ssh_pattern, repo_url)
    
    if ssh_match:
        host = ssh_match.group(1)
        path = ssh_match.group(2)
        
        # 如果提供了server_url，使用它
        if server_url:
            # 从server_url提取协议和主机
            server_match = re.match(r'^(https?://[^/]+)', server_url)
            if server_match:
                base_url = server_match.group(1)
                # 插入认证信息
                auth_url = base_url.replace('://', f'://{encoded_user}:{encoded_password}@')
                return f"{auth_url}/{path}"
        
        # 默认使用http
        return f"http://{encoded_user}:{encoded_password}@{host}/{path}"
    
    # 解析HTTP/HTTPS URL
    http_pattern = r'^(https?)://([^/]+)(.*)$'
    http_match = re.match(http_pattern, repo_url)
    
    if http_match:
        protocol = http_match.group(1)
        host = http_match.group(2)
        path = http_match.group(3)
        
        # 检查是否已有认证信息
        if '@' in host:
            # 已有认证，替换它
            host = host.split('@')[-1]
        
        return f"{protocol}://{encoded_user}:{encoded_password}@{host}{path}"
    
    # 无法解析，返回原始URL
    logger.warning(f"无法解析仓库URL格式: {repo_url}")
    return repo_url


def build_git_auth(platform: str, token: str = '', http_user: str = '', http_password: str = '') -> dict:
    """
    构建Git API认证信息
    
    优先使用API Token，如果没有则使用HTTP Basic认证
    
    Returns:
        {"headers": dict, "auth": tuple or None}
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
    
    return {"headers": headers, "auth": auth}
