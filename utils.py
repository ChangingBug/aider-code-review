"""
工具函数模块
"""
import logging
import re
from typing import List, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("aider-reviewer")


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
    """
    return [f for f in files if any(f.endswith(ext) for ext in valid_extensions)]


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
    return """请审查这个Commit的代码变更。

重点关注：
1. 逻辑错误和潜在Bug
2. 安全漏洞（SQL注入、XSS、敏感信息泄露等）
3. 代码风格和最佳实践
4. 性能问题

输出格式要求：
- 使用Markdown格式
- 按严重程度分类（🔴 严重 / 🟡 警告 / 🔵 建议）
- 每个问题包含：文件名、问题描述、修复建议

⚠️ 重要：不要输出任何代码编辑块，只提供文字审查报告。"""


def get_mr_prompt(target_branch: str) -> str:
    """获取Merge Request审查的Prompt模板"""
    return f"""这是一个合并请求(Merge Request)，目标分支: {target_branch}

请对当前分支相对于目标分支的所有变更进行全面审查。

审查要点：
1. **架构影响**: 评估变更对整体架构的影响
2. **API兼容性**: 检查是否有Breaking Changes
3. **代码质量**: 代码可读性、可维护性、测试覆盖
4. **安全性**: 潜在的安全风险
5. **性能**: 可能的性能瓶颈

输出格式要求：
- 使用Markdown格式
- 提供整体评估摘要
- 按模块/文件分组列出具体问题
- 给出改进建议

⚠️ 重要：不要输出任何代码编辑块，只提供文字审查报告。"""


def sanitize_branch_name(ref: str) -> str:
    """从Git ref中提取分支名"""
    return ref.replace('refs/heads/', '').replace('refs/tags/', '')
