"""
报告导出服务

支持 Markdown 和 HTML 格式导出
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from services.issue_parser import ParsedIssue, ReviewSummary, IssueSeverity


class ReportExporter:
    """报告导出器"""
    
    SEVERITY_ICONS = {
        "critical": "🔴",
        "warning": "🟡",
        "suggestion": "🔵",
        "info": "ℹ️",
    }
    
    SEVERITY_LABELS = {
        "critical": "严重",
        "warning": "警告",
        "suggestion": "建议",
        "info": "信息",
    }
    
    def export_markdown(self, review_data: Dict[str, Any], 
                        issues: List[ParsedIssue], 
                        summary: ReviewSummary) -> str:
        """导出为 Markdown 格式"""
        lines = []
        
        # 标题
        lines.append(f"# 代码审查报告")
        lines.append("")
        lines.append(f"**项目**: {review_data.get('project_name', '-')}")
        lines.append(f"**审查策略**: {review_data.get('strategy', '-')}")
        lines.append(f"**作者**: {review_data.get('author_name', '-')}")
        lines.append(f"**时间**: {review_data.get('started_at', '-')}")
        lines.append("")
        
        # 总结
        lines.append("## 📊 审查总结")
        lines.append("")
        lines.append(f"| 项目 | 结果 |")
        lines.append(f"|------|------|")
        lines.append(f"| 质量评分 | **{summary.overall_score:.0f}/100** |")
        lines.append(f"| 评审结论 | {summary.verdict} |")
        lines.append(f"| 风险等级 | {summary.risk_level.upper()} |")
        lines.append("")
        
        # 关键发现
        if summary.key_findings:
            lines.append("### 关键发现")
            for finding in summary.key_findings:
                lines.append(f"- {finding}")
            lines.append("")
        
        # 改进建议
        if summary.recommendations:
            lines.append("### 改进建议")
            for rec in summary.recommendations:
                lines.append(f"- {rec}")
            lines.append("")
        
        # 问题统计
        lines.append("## 📋 问题统计")
        lines.append("")
        
        critical = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
        warning = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
        suggestion = sum(1 for i in issues if i.severity == IssueSeverity.SUGGESTION)
        info = sum(1 for i in issues if i.severity == IssueSeverity.INFO)
        
        lines.append(f"| 级别 | 数量 |")
        lines.append(f"|------|------|")
        lines.append(f"| 🔴 严重 | {critical} |")
        lines.append(f"| 🟡 警告 | {warning} |")
        lines.append(f"| 🔵 建议 | {suggestion} |")
        lines.append(f"| ℹ️ 信息 | {info} |")
        lines.append(f"| **总计** | **{len(issues)}** |")
        lines.append("")
        
        # 问题详情
        if issues:
            lines.append("## 🔍 问题详情")
            lines.append("")
            
            for idx, issue in enumerate(issues, 1):
                icon = self.SEVERITY_ICONS.get(issue.severity.value, "•")
                label = self.SEVERITY_LABELS.get(issue.severity.value, issue.severity.value)
                
                # 标题行
                location = ""
                if issue.file_path:
                    location = f" `{issue.file_path}"
                    if issue.line_number:
                        location += f":{issue.line_number}"
                    location += "`"
                
                lines.append(f"### {idx}. {icon} [{label}] {issue.title}{location}")
                lines.append("")
                
                # 描述
                if issue.description:
                    lines.append(issue.description)
                    lines.append("")
                
                # 代码片段
                if issue.code_snippet:
                    lines.append("**问题代码**:")
                    lines.append("```")
                    lines.append(issue.code_snippet)
                    lines.append("```")
                    lines.append("")
                
                # 建议
                if issue.suggestion:
                    lines.append(f"**建议**: {issue.suggestion}")
                    lines.append("")
                
                lines.append("---")
                lines.append("")
        
        # 原始报告
        if review_data.get('report'):
            lines.append("## 📄 原始报告")
            lines.append("")
            lines.append(review_data['report'])
            lines.append("")
        
        # 页脚
        lines.append("---")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        
        return "\n".join(lines)
    
    def export_html(self, review_data: Dict[str, Any], 
                    issues: List[ParsedIssue], 
                    summary: ReviewSummary) -> str:
        """导出为 HTML 格式"""
        
        # 样式
        styles = """
        <style>
            * { box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .report { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            h1 { color: #1a1a1a; border-bottom: 3px solid #3b82f6; padding-bottom: 10px; }
            h2 { color: #333; margin-top: 30px; }
            .meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 6px; }
            .meta-item { }
            .meta-label { font-weight: 600; color: #666; }
            .summary-box { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }
            .summary-item { padding: 20px; border-radius: 8px; text-align: center; }
            .summary-item.score { background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; }
            .summary-item.verdict { background: #f0fdf4; border: 1px solid #86efac; }
            .summary-item.risk { background: #fef2f2; border: 1px solid #fca5a5; }
            .summary-value { font-size: 2em; font-weight: bold; }
            .summary-label { font-size: 0.9em; opacity: 0.8; }
            .stats-table { width: 100%; border-collapse: collapse; margin: 20px 0; }
            .stats-table th, .stats-table td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
            .stats-table th { background: #f8f9fa; font-weight: 600; }
            .issue-card { border: 1px solid #e5e7eb; border-radius: 8px; margin: 15px 0; overflow: hidden; }
            .issue-header { padding: 15px; display: flex; align-items: center; gap: 10px; }
            .issue-header.critical { background: #fef2f2; border-left: 4px solid #ef4444; }
            .issue-header.warning { background: #fffbeb; border-left: 4px solid #f59e0b; }
            .issue-header.suggestion { background: #eff6ff; border-left: 4px solid #3b82f6; }
            .issue-header.info { background: #f8f9fa; border-left: 4px solid #9ca3af; }
            .issue-icon { font-size: 1.5em; }
            .issue-title { font-weight: 600; flex: 1; }
            .issue-location { font-family: monospace; font-size: 0.9em; color: #666; background: #f3f4f6; padding: 2px 8px; border-radius: 4px; }
            .issue-body { padding: 15px; background: white; }
            .code-block { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 6px; font-family: 'Monaco', 'Consolas', monospace; font-size: 0.9em; overflow-x: auto; }
            .suggestion-box { background: #f0fdf4; border: 1px solid #86efac; padding: 12px; border-radius: 6px; margin-top: 10px; }
            .suggestion-box::before { content: '💡 建议: '; font-weight: 600; }
            .findings-list, .recommendations-list { list-style: none; padding: 0; }
            .findings-list li::before { content: '• '; color: #3b82f6; font-weight: bold; }
            .recommendations-list li::before { content: '→ '; color: #10b981; font-weight: bold; }
            .footer { margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 0.9em; text-align: center; }
            @media print {
                body { background: white; }
                .report { box-shadow: none; }
            }
        </style>
        """
        
        # 问题统计
        critical = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
        warning = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
        suggestion_count = sum(1 for i in issues if i.severity == IssueSeverity.SUGGESTION)
        info_count = sum(1 for i in issues if i.severity == IssueSeverity.INFO)
        
        # 构建 HTML
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='zh-CN'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"<title>代码审查报告 - {review_data.get('project_name', '')}</title>",
            styles,
            "</head>",
            "<body>",
            "<div class='report'>",
            
            # 标题
            "<h1>📋 代码审查报告</h1>",
            
            # 元信息
            "<div class='meta'>",
            f"<div class='meta-item'><span class='meta-label'>项目:</span> {self._escape(review_data.get('project_name', '-'))}</div>",
            f"<div class='meta-item'><span class='meta-label'>审查策略:</span> {review_data.get('strategy', '-')}</div>",
            f"<div class='meta-item'><span class='meta-label'>作者:</span> {self._escape(review_data.get('author_name', '-'))}</div>",
            f"<div class='meta-item'><span class='meta-label'>时间:</span> {review_data.get('started_at', '-')}</div>",
            "</div>",
            
            # 总结卡片
            "<div class='summary-box'>",
            "<div class='summary-item score'>",
            f"<div class='summary-value'>{summary.overall_score:.0f}</div>",
            "<div class='summary-label'>质量评分</div>",
            "</div>",
            "<div class='summary-item verdict'>",
            f"<div class='summary-value' style='color: #16a34a'>{summary.verdict}</div>",
            "<div class='summary-label'>评审结论</div>",
            "</div>",
            "<div class='summary-item risk'>",
            f"<div class='summary-value' style='color: #dc2626'>{summary.risk_level.upper()}</div>",
            "<div class='summary-label'>风险等级</div>",
            "</div>",
            "</div>",
        ]
        
        # 关键发现
        if summary.key_findings:
            html_parts.append("<h2>🔍 关键发现</h2>")
            html_parts.append("<ul class='findings-list'>")
            for finding in summary.key_findings:
                html_parts.append(f"<li>{self._escape(finding)}</li>")
            html_parts.append("</ul>")
        
        # 改进建议
        if summary.recommendations:
            html_parts.append("<h2>💡 改进建议</h2>")
            html_parts.append("<ul class='recommendations-list'>")
            for rec in summary.recommendations:
                html_parts.append(f"<li>{self._escape(rec)}</li>")
            html_parts.append("</ul>")
        
        # 问题统计表
        html_parts.extend([
            "<h2>📊 问题统计</h2>",
            "<table class='stats-table'>",
            "<tr><th>级别</th><th>数量</th></tr>",
            f"<tr><td>🔴 严重</td><td>{critical}</td></tr>",
            f"<tr><td>🟡 警告</td><td>{warning}</td></tr>",
            f"<tr><td>🔵 建议</td><td>{suggestion_count}</td></tr>",
            f"<tr><td>ℹ️ 信息</td><td>{info_count}</td></tr>",
            f"<tr><th>总计</th><th>{len(issues)}</th></tr>",
            "</table>",
        ])
        
        # 问题详情
        if issues:
            html_parts.append("<h2>📝 问题详情</h2>")
            
            for issue in issues:
                severity_class = issue.severity.value
                icon = self.SEVERITY_ICONS.get(issue.severity.value, "•")
                label = self.SEVERITY_LABELS.get(issue.severity.value, issue.severity.value)
                
                location_html = ""
                if issue.file_path:
                    location = issue.file_path
                    if issue.line_number:
                        location += f":{issue.line_number}"
                    location_html = f"<span class='issue-location'>{self._escape(location)}</span>"
                
                html_parts.extend([
                    f"<div class='issue-card'>",
                    f"<div class='issue-header {severity_class}'>",
                    f"<span class='issue-icon'>{icon}</span>",
                    f"<span class='issue-title'>[{label}] {self._escape(issue.title)}</span>",
                    location_html,
                    "</div>",
                    "<div class='issue-body'>",
                ])
                
                if issue.description:
                    html_parts.append(f"<p>{self._escape(issue.description)}</p>")
                
                if issue.code_snippet:
                    html_parts.append("<div class='code-block'>")
                    html_parts.append(self._escape(issue.code_snippet))
                    html_parts.append("</div>")
                
                if issue.suggestion:
                    html_parts.append(f"<div class='suggestion-box'>{self._escape(issue.suggestion)}</div>")
                
                html_parts.extend([
                    "</div>",
                    "</div>",
                ])
        
        # 页脚
        html_parts.extend([
            f"<div class='footer'>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
            "</div>",
            "</body>",
            "</html>",
        ])
        
        return "\n".join(html_parts)
    
    def _escape(self, text: str) -> str:
        """HTML 转义"""
        if not text:
            return ""
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


# 单例
report_exporter = ReportExporter()
