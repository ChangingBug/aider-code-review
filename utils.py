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
    """获取Commit审查的Prompt模板（增强版，支持 Repo Map 分析）"""
    return """# Role Context
你是由 DevOps 团队部署的 **高级技术专家（Senior Technical Architect）**。
你的任务是对提交的代码变更（Diff）进行深度评审。
请注意：**你不需要修改代码，只需要输出一份结构清晰的评审报告。**

# Core Capability: Repo Map Analysis
Aider 已为你提供了项目的 Repository Map（仓库地图）。
请**务必**利用这一上下文信息，不要只盯着变更的几行代码，要检查：
1. **引用链断裂**：变更的函数签名是否破坏了未修改文件中的调用？
2. **架构一致性**：新代码是否符合项目中现有的分层设计（如 MVC、DDD）？
3. **重复造轮子**：项目中是否已有类似的工具类或方法？

# Analysis Dimensions
请从以下 5 个维度进行分析：

## 1. 全局影响分析 (High Criticality) 🚨
* 基于 Repo Map，列出受此变更影响的模块和类。
* 是否存在"修改了接口但未更新所有调用方"的风险？

## 2. 逻辑与健壮性 (Logic) 🧠
* 边界条件（Null/Empty/Negative）是否处理完善？
* 是否存在明显的并发安全问题？
* 异常处理是否合理？

## 3. 安全性 (Security) 🛡️
* 是否存在 SQL 注入、XSS 或敏感信息泄露？
* 权限校验逻辑是否缺失？

## 4. 可维护性与规范 (Maintainability) 🧹
* 命名是否符合项目现有风格？
* 代码是否过于复杂？

## 5. 性能 (Performance) 🚀
* 是否存在 N+1 查询问题？
* 是否存在大对象低效操作？

# Output Format (Strict Markdown)
请直接输出以下格式的 Markdown 报告：

---
### 🏗️ Code Review Report

**Risk Score (0-100):** [分数，100为高风险]
**Summary:** [一句话总结变更内容]

---

#### 🔴 Critical Issues (必须修复)

**问题 1: [问题标题]**
- 📍 **位置**: `ClassName.methodName()` @ `path/to/file.py:行号`
- ❌ **问题代码**:
```python
# 有问题的代码片段
```
- ✅ **建议修复**:
```python
# 修复后的代码
```
- 💡 **原因**: [为什么这是问题，可能导致什么后果]

---

#### 🟡 Potential Risks (建议关注)

**风险 1: [风险标题]**
- 📍 **位置**: `ClassName.methodName()` @ `path/to/file.py:行号`
- ⚠️ **风险点**: [具体说明]
- 💡 **建议**: [如何规避或改进]

---

#### 🟢 Suggestions (优化建议)

* **[建议标题]**: [具体说明，可包含代码示例]

---

#### 🔍 Repo Map Insight (全仓库视角)

* [基于 Repo Map 发现的问题，如重复代码、架构不一致等]

---
"""




def get_mr_prompt(target_branch: str) -> str:
    """获取Merge Request审查的Prompt模板（增强版，支持 Repo Map 分析）"""
    return f"""# Role Context
你是由 DevOps 团队部署的 **高级技术专家（Senior Technical Architect）**。
你的任务是对 Merge Request（目标分支: {target_branch}）的代码变更进行深度评审。
请注意：**你不需要修改代码，只需要输出一份结构清晰的评审报告。**

# Core Capability: Repo Map Analysis
Aider 已为你提供了项目的 Repository Map（仓库地图）。
请**务必**利用这一上下文信息，不要只盯着变更的几行代码，要检查：
1. **引用链断裂**：变更的函数签名是否破坏了未修改文件中的调用？
2. **架构一致性**：新代码是否符合项目中现有的分层设计（如 MVC、DDD）？
3. **重复造轮子**：项目中是否已有类似的工具类或方法？

# Analysis Dimensions
请从以下 5 个维度进行分析：

## 1. 全局影响分析 (High Criticality) 🚨
* 基于 Repo Map，列出受此变更影响的模块和类。
* 是否存在"修改了接口但未更新所有调用方"的风险？

## 2. 逻辑与健壮性 (Logic) 🧠
* 边界条件（Null/Empty/Negative）是否处理完善？
* 是否存在明显的并发安全问题？
* 异常处理是否合理？

## 3. 安全性 (Security) 🛡️
* 是否存在 SQL 注入、XSS 或敏感信息泄露？
* 权限校验逻辑是否缺失？

## 4. 可维护性与规范 (Maintainability) 🧹
* 命名是否符合项目现有风格？
* 代码是否过于复杂？

## 5. 性能 (Performance) 🚀
* 是否存在 N+1 查询问题？
* 是否存在大对象低效操作？

# Output Format (Strict Markdown)
请直接输出以下格式的 Markdown 报告：

---
### 🏗️ Code Review Report (Merge Request)

**Target Branch:** {target_branch}
**Risk Score (0-100):** [分数，100为高风险]
**Summary:** [一句话总结变更内容]
**Merge Recommendation:** [✅ 可合并 / ⚠️ 需修改后合并 / ❌ 建议拒绝]

---

#### 🔴 Critical Issues (必须修复)

**问题 1: [问题标题]**
- 📍 **位置**: `ClassName.methodName()` @ `path/to/file.py:行号`
- ❌ **问题代码**:
```python
# 有问题的代码片段
```
- ✅ **建议修复**:
```python
# 修复后的代码
```
- 💡 **原因**: [为什么这是问题，可能导致什么后果]

---

#### 🟡 Potential Risks (建议关注)

**风险 1: [风险标题]**
- 📍 **位置**: `ClassName.methodName()` @ `path/to/file.py:行号`
- ⚠️ **风险点**: [具体说明]
- 💡 **建议**: [如何规避或改进]

---

#### 🟢 Suggestions (优化建议)

* **[建议标题]**: [具体说明，可包含代码示例]

---

#### 🔍 Repo Map Insight (全仓库视角)

* [基于 Repo Map 发现的问题，如重复代码、架构不一致等]

---
"""




# ==================== Token 估算与分批工具 ====================

def estimate_file_tokens(filepath: str) -> int:
    """
    估算文件的 token 数
    
    简单估算规则:
    - ASCII 字符: 约 4 字符 = 1 token
    - 非 ASCII (中文等): 约 1.5 字符 = 1 token
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        ascii_chars = sum(1 for c in content if ord(c) < 128)
        non_ascii = len(content) - ascii_chars
        
        return int(ascii_chars / 4 + non_ascii / 1.5)
    except Exception as e:
        logger.warning(f"估算文件 token 失败 {filepath}: {e}")
        return 0


def split_files_by_tokens(files: List[str], work_dir: str, max_tokens: int) -> List[List[str]]:
    """
    按 token 限制将文件分批
    
    算法:
    1. 估算每个文件的 token
    2. 大文件优先放置（贪心算法）
    3. 确保每批不超过 max_tokens
    4. 单个文件超限时单独成批
    
    Args:
        files: 文件列表（相对路径）
        work_dir: 工作目录
        max_tokens: 单批次最大 token 数
    
    Returns:
        分批后的文件列表，每个子列表为一个批次
    """
    import os
    
    # 计算每个文件的 token
    file_tokens = {}
    for f in files:
        filepath = os.path.join(work_dir, f)
        file_tokens[f] = estimate_file_tokens(filepath)
    
    # 按 token 降序排列（大文件优先）
    sorted_files = sorted(files, key=lambda x: -file_tokens.get(x, 0))
    
    batches = []
    current_batch = []
    current_tokens = 0
    
    for f in sorted_files:
        ft = file_tokens.get(f, 0)
        
        # 如果单个文件就超限，单独成批
        if ft > max_tokens:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            batches.append([f])
            logger.warning(f"文件 {f} 单独超限 ({ft} tokens)，将单独审查")
            continue
        
        # 如果加入当前批次会超限，开启新批次
        if current_tokens + ft > max_tokens and current_batch:
            batches.append(current_batch)
            current_batch = [f]
            current_tokens = ft
        else:
            current_batch.append(f)
            current_tokens += ft
    
    if current_batch:
        batches.append(current_batch)
    
    return batches if batches else [files]


def merge_batch_reports(batch_reports: List[tuple]) -> str:
    """
    合并多批次审查报告
    
    Args:
        batch_reports: [(files, report), ...] 每批次的文件列表和报告
    
    Returns:
        合并后的完整报告
    """
    if len(batch_reports) == 1:
        return batch_reports[0][1]
    
    parts = [
        "# 🏗️ 代码审查报告（分批执行）\n\n",
        f"> 本次审查因内容较多，分 **{len(batch_reports)}** 批执行，每批次保留完整仓库上下文。\n\n"
    ]
    
    for i, (files, report) in enumerate(batch_reports, 1):
        file_list = ', '.join(f'`{f}`' for f in files[:3])
        if len(files) > 3:
            file_list += f' 等 {len(files)} 个文件'
        
        parts.append(f"---\n\n## 📦 批次 {i}: {file_list}\n\n")
        parts.append(report + "\n\n")
    
    return ''.join(parts)


def sanitize_branch_name(ref: str) -> str:
    """从Git ref中提取分支名"""
    return ref.replace('refs/heads/', '').replace('refs/tags/', '').replace('refs/merge-requests/', '').replace('refs/pull/', '')



def extract_project_path(url: str) -> Optional[str]:
    """
    从Git URL提取项目路径 (group/repo)
    支持 SSH 和 HTTP(S) 格式
    """
    if not url:
        return None
        
    # SSH格式: git@host:group/project.git
    ssh_match = re.match(r'git@[^:]+:(.+?)(?:\.git)?$', url)
    if ssh_match:
        return ssh_match.group(1)
    
    # HTTP格式: http(s)://host/group/project.git
    http_match = re.match(r'https?://[^/]+/(.+?)(?:\.git)?$', url)
    if http_match:
        return http_match.group(1)
    
    return None


def convert_to_http_auth_url(repo_url: str, http_user: str = "", http_password: str = "", 
                            server_url: str = "", token: str = "") -> str:
    """
    将Git仓库URL转换为带HTTP认证或Token认证的URL
    
    支持:
    - 用户名/密码 (Basic Auth)
    - Token (注入到URL: https://token@host/path)
    
    Args:
        repo_url: 原始仓库URL
        http_user: HTTP认证用户名
        http_password: HTTP认证密码
        token: API Token (如果提供则优先使用Token注入)
        server_url: Git服务器基础URL (用于SSH转换)
    """
    from urllib.parse import quote, urlparse, urlunparse
    
    if token:
        # 使用Token注入格式: https://token@host/path
        parsed = urlparse(repo_url)
        # 如果是SSH格式，需要转换为HTTP格式
        if not parsed.scheme or parsed.scheme == 'ssh':
            path = extract_project_path(repo_url)
            if server_url:
                base_parsed = urlparse(server_url)
                return urlunparse((base_parsed.scheme, f"{token}@{base_parsed.netloc}", f"/{path}", '', '', ''))
            # 无法推导，尝试解析主机
            ssh_match = re.match(r'git@([^:]+):', repo_url)
            host = ssh_match.group(1) if ssh_match else "localhost"
            return f"http://{token}@{host}/{path}"
            
        return urlunparse((
            parsed.scheme,
            f"{token}@{parsed.netloc}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))

    if not http_user or not http_password:
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
            headers["Authorization"] = f"Bearer {token}"
            headers["Accept"] = "application/vnd.github.v3+json"
    elif http_user and http_password:
        # 使用HTTP Basic认证
        auth = (http_user, http_password)
    
    return {"headers": headers, "auth": auth}
