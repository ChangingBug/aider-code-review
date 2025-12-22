"""
问题解析服务

解析 Aider 输出，提取结构化问题信息
"""
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class IssueSeverity(Enum):
    """问题严重程度"""
    CRITICAL = "critical"    # 🔴 严重
    WARNING = "warning"      # 🟡 警告
    SUGGESTION = "suggestion"  # 🔵 建议
    INFO = "info"            # ℹ️ 信息


@dataclass
class ParsedIssue:
    """解析后的问题"""
    severity: IssueSeverity
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    category: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "suggestion": self.suggestion,
            "category": self.category,
        }


@dataclass
class ReviewSummary:
    """审查总结"""
    overall_score: float
    verdict: str  # 通过/需改进/需重点关注
    key_findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    risk_level: str = "low"  # low/medium/high
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "verdict": self.verdict,
            "key_findings": self.key_findings,
            "recommendations": self.recommendations,
            "risk_level": self.risk_level,
        }


class IssueParser:
    """问题解析器"""
    
    # 严重程度关键词映射
    SEVERITY_PATTERNS = {
        IssueSeverity.CRITICAL: [
            r'🔴', r'严重', r'critical', r'security', r'vulnerability',
            r'漏洞', r'危险', r'dangerous', r'error', r'错误'
        ],
        IssueSeverity.WARNING: [
            r'🟡', r'警告', r'warning', r'注意', r'caution', r'问题'
        ],
        IssueSeverity.SUGGESTION: [
            r'🔵', r'建议', r'suggestion', r'优化', r'改进', 
            r'recommend', r'improvement', r'consider'
        ],
        IssueSeverity.INFO: [
            r'ℹ️', r'信息', r'info', r'note', r'提示'
        ],
    }
    
    # 问题类别关键词
    CATEGORY_PATTERNS = {
        "security": [r'security', r'安全', r'注入', r'injection', r'xss', r'csrf', r'漏洞'],
        "logic": [r'逻辑', r'logic', r'bug', r'缺陷', r'错误'],
        "performance": [r'性能', r'performance', r'优化', r'效率', r'慢'],
        "style": [r'风格', r'style', r'格式', r'命名', r'naming', r'可读性'],
        "maintainability": [r'可维护', r'maintainability', r'复杂度', r'重复', r'耦合'],
        "documentation": [r'文档', r'注释', r'comment', r'documentation'],
    }
    
    def parse_report(self, raw_report: str) -> List[ParsedIssue]:
        """解析审查报告，提取结构化问题列表"""
        if not raw_report:
            return []
        
        # 预处理：移除 <think>...</think> 标签内容
        import re
        cleaned_report = re.sub(r'<think>[\s\S]*?</think>', '', raw_report, flags=re.IGNORECASE)
        cleaned_report = re.sub(r'\[think\][\s\S]*?\[/think\]', '', cleaned_report, flags=re.IGNORECASE)
        
        issues = []
        
        # 尝试多种解析策略
        issues = self._parse_structured_format(cleaned_report)
        
        if not issues:
            issues = self._parse_markdown_format(cleaned_report)
        
        if not issues:
            issues = self._parse_free_text(cleaned_report)
        
        return issues
    
    def _parse_structured_format(self, text: str) -> List[ParsedIssue]:
        """解析结构化格式（带有明确标记的问题列表）"""
        issues = []
        
        # 匹配模式: 🔴/🟡/🔵 [文件:行号] 标题
        pattern = r'([🔴🟡🔵ℹ️])\s*(?:\[([^\]]+?)(?::(\d+))?\])?\s*(.+?)(?:\n|$)'
        
        for match in re.finditer(pattern, text):
            emoji, file_path, line_num, title = match.groups()
            
            # 确定严重程度
            severity = self._detect_severity(emoji + " " + title)
            
            # 提取后续描述
            start_pos = match.end()
            description = self._extract_description(text, start_pos)
            
            # 提取建议
            suggestion = self._extract_suggestion(description)
            
            # 提取代码片段
            code_snippet = self._extract_code_snippet(description)
            
            # 确定类别
            category = self._detect_category(title + " " + description)
            
            issues.append(ParsedIssue(
                severity=severity,
                title=title.strip(),
                description=description.strip() if description else "",
                file_path=file_path,
                line_number=int(line_num) if line_num else None,
                code_snippet=code_snippet,
                suggestion=suggestion,
                category=category,
            ))
        
        return issues
    
    def _parse_markdown_format(self, text: str) -> List[ParsedIssue]:
        """解析 Markdown 格式（标题 + 描述）"""
        issues = []
        
        # 方案1：匹配 ### 或 ## 标题
        sections = re.split(r'\n(?=#{1,4}\s)', text)
        
        for section in sections:
            if not section.strip():
                continue
            
            # 提取标题
            title_match = re.match(r'#{1,4}\s*(.+)', section)
            if not title_match:
                continue
            
            title = title_match.group(1).strip()
            description = section[title_match.end():].strip()
            
            # 跳过通用标题（如"代码审查报告"、"总结"等）
            skip_titles = ['代码审查', '总结', 'summary', '概述', 'overview', '审查报告', '结论']
            if any(skip in title.lower() for skip in skip_titles):
                continue
            
            # 检查是否像问题描述
            severity = self._detect_severity(title + " " + description)
            if severity == IssueSeverity.INFO and not self._looks_like_issue(title, description):
                continue
            
            # 提取文件路径和行号
            file_path, line_num = self._extract_file_location(title + " " + description)
            
            issues.append(ParsedIssue(
                severity=severity,
                title=title,
                description=description,
                file_path=file_path,
                line_number=line_num,
                code_snippet=self._extract_code_snippet(description),
                suggestion=self._extract_suggestion(description),
                category=self._detect_category(title + " " + description),
            ))
        
        # 方案2：匹配数字列表格式（1. xxx  2. xxx）
        if not issues:
            list_pattern = r'(?:^|\n)(\d+)[.、]\s*(.+?)(?=\n\d+[.、]\s|\n\n|$)'
            for match in re.finditer(list_pattern, text, re.DOTALL):
                content = match.group(2).strip()
                if len(content) < 10:
                    continue
                    
                # 提取第一行作为标题
                lines = content.split('\n')
                title = lines[0][:100]
                description = '\n'.join(lines[1:]) if len(lines) > 1 else ''
                
                severity = self._detect_severity(content)
                if severity == IssueSeverity.INFO and not self._looks_like_issue(title, content):
                    continue
                
                file_path, line_num = self._extract_file_location(content)
                
                issues.append(ParsedIssue(
                    severity=severity,
                    title=title,
                    description=description,
                    file_path=file_path,
                    line_number=line_num,
                    code_snippet=self._extract_code_snippet(content),
                    suggestion=self._extract_suggestion(content),
                    category=self._detect_category(content),
                ))
        
        return issues
    
    def _parse_free_text(self, text: str) -> List[ParsedIssue]:
        """解析自由文本（作为单个问题或按段落拆分）"""
        issues = []
        
        # 按双换行分段
        paragraphs = re.split(r'\n\n+', text)
        
        for para in paragraphs:
            if len(para.strip()) < 20:  # 太短的段落跳过
                continue
            
            severity = self._detect_severity(para)
            
            # 只保留看起来像问题的段落
            if severity != IssueSeverity.INFO or self._looks_like_issue("", para):
                # 提取第一句作为标题
                first_sentence = re.split(r'[。.!！\n]', para)[0]
                
                issues.append(ParsedIssue(
                    severity=severity,
                    title=first_sentence[:100] + ("..." if len(first_sentence) > 100 else ""),
                    description=para,
                    file_path=None,
                    line_number=None,
                    code_snippet=self._extract_code_snippet(para),
                    suggestion=self._extract_suggestion(para),
                    category=self._detect_category(para),
                ))
        
        return issues
    
    def _detect_severity(self, text: str) -> IssueSeverity:
        """检测问题严重程度"""
        text_lower = text.lower()
        
        for severity, patterns in self.SEVERITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return severity
        
        return IssueSeverity.INFO
    
    def _detect_category(self, text: str) -> Optional[str]:
        """检测问题类别"""
        text_lower = text.lower()
        
        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return category
        
        return None
    
    def _looks_like_issue(self, title: str, description: str) -> bool:
        """判断是否看起来像问题描述"""
        combined = (title + " " + description).lower()
        
        issue_indicators = [
            r'should', r'could', r'建议', r'可以', r'需要',
            r'问题', r'issue', r'bug', r'error', r'warning',
            r'fix', r'修复', r'改进', r'优化'
        ]
        
        return any(re.search(pat, combined) for pat in issue_indicators)
    
    def _extract_description(self, text: str, start_pos: int) -> str:
        """提取问题描述（从起始位置到下一个问题标记）"""
        # 查找下一个问题标记
        next_match = re.search(r'[🔴🟡🔵ℹ️]|\n##', text[start_pos:])
        
        if next_match:
            return text[start_pos:start_pos + next_match.start()]
        return text[start_pos:start_pos + 500]  # 最多500字符
    
    def _extract_suggestion(self, text: str) -> Optional[str]:
        """提取建议修改"""
        patterns = [
            r'建议[：:]\s*(.+?)(?:\n|$)',
            r'suggestion[：:]\s*(.+?)(?:\n|$)',
            r'推荐[：:]\s*(.+?)(?:\n|$)',
            r'应该[：:]\s*(.+?)(?:\n|$)',
            r'改为[：:]\s*(.+?)(?:\n|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_code_snippet(self, text: str) -> Optional[str]:
        """提取代码片段"""
        # 匹配代码块
        code_match = re.search(r'```[\w]*\n([\s\S]*?)```', text)
        if code_match:
            return code_match.group(1).strip()
        
        # 匹配行内代码
        inline_codes = re.findall(r'`([^`]+)`', text)
        if inline_codes:
            return "\n".join(inline_codes[:3])  # 最多3个
        
        return None
    
    def _extract_file_location(self, text: str) -> tuple:
        """提取文件路径和行号"""
        # 常见格式: file.py:123, file.py line 123, file.py (line 123)
        patterns = [
            r'([a-zA-Z0-9_./\\-]+\.[a-zA-Z]+)[:\s]+(?:line\s*)?(\d+)',
            r'([a-zA-Z0-9_./\\-]+\.[a-zA-Z]+)\s*\(\s*(?:line\s*)?(\d+)\s*\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1), int(match.group(2))
        
        # 仅文件路径
        file_match = re.search(r'([a-zA-Z0-9_./\\-]+\.[a-zA-Z]{2,4})', text)
        if file_match:
            return file_match.group(1), None
        
        return None, None
    
    def generate_summary(self, issues: List[ParsedIssue], quality_score: float = None) -> ReviewSummary:
        """生成审查总结"""
        if not issues and quality_score is None:
            return ReviewSummary(
                overall_score=100,
                verdict="通过",
                key_findings=["未发现问题"],
                recommendations=[],
                risk_level="low"
            )
        
        # 统计问题
        critical_count = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
        warning_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
        suggestion_count = sum(1 for i in issues if i.severity == IssueSeverity.SUGGESTION)
        
        # 计算评分（如果没有提供）
        if quality_score is None:
            quality_score = max(0, 100 - (critical_count * 20 + warning_count * 5 + suggestion_count * 1))
        
        # 确定评价结论
        if critical_count > 0:
            verdict = "需重点关注"
            risk_level = "high"
        elif warning_count > 2:
            verdict = "需改进"
            risk_level = "medium"
        elif quality_score >= 80:
            verdict = "通过"
            risk_level = "low"
        else:
            verdict = "需改进"
            risk_level = "medium"
        
        # 生成关键发现
        key_findings = []
        if critical_count > 0:
            key_findings.append(f"发现 {critical_count} 个严重问题需要立即修复")
        if warning_count > 0:
            key_findings.append(f"发现 {warning_count} 个警告需要关注")
        
        # 按类别统计
        categories = {}
        for issue in issues:
            if issue.category:
                categories[issue.category] = categories.get(issue.category, 0) + 1
        
        if categories:
            top_category = max(categories, key=categories.get)
            key_findings.append(f"主要问题类型: {top_category} ({categories[top_category]} 个)")
        
        # 生成建议
        recommendations = []
        if critical_count > 0:
            recommendations.append("优先修复标记为严重的安全和逻辑问题")
        if "security" in categories:
            recommendations.append("进行安全审查，确保没有注入风险")
        if "style" in categories:
            recommendations.append("考虑引入代码格式化工具统一风格")
        if suggestion_count > 3:
            recommendations.append("考虑重构以提高代码可维护性")
        
        return ReviewSummary(
            overall_score=quality_score,
            verdict=verdict,
            key_findings=key_findings if key_findings else ["代码质量良好"],
            recommendations=recommendations if recommendations else ["继续保持良好的编码习惯"],
            risk_level=risk_level
        )


# 单例
issue_parser = IssueParser()
