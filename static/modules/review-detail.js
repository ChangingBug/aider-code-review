/**
 * 审查详情页面模块（增强版）
 * 
 * 功能：
 * - 选项卡导航（概览/问题/报告）
 * - 问题卡片与代码对比视图
 * - 报告下载
 */

import { API } from './api.js';
import { formatDate, getStatusClass, getStatusText, escapeHtml, renderScore } from './utils.js';

let currentReview = null;
let currentIssues = [];
let currentSummary = null;
let activeTab = 'overview';

// ==================== 主入口 ====================

export async function showReviewDetail(taskId) {
    const modal = document.getElementById('review-modal');
    const content = document.getElementById('review-modal-content');

    if (!modal || !content) {
        console.error('Review detail modal elements not found!');
        return;
    }

    // 显示加载状态
    content.innerHTML = `
        <div class="review-detail-loading">
            <div class="spinner"></div>
            <p>正在加载审查详情...</p>
        </div>
    `;

    // 显示模态框
    modal.style.display = 'flex';
    modal.classList.add('review-detail-modal');
    // 强制重绘以确保过渡效果（可选，但推荐）
    // void modal.offsetWidth; 
    modal.classList.add('active'); // 关键：触发CSS的opacity/visibility变化

    try {
        // 获取完整审查数据
        const data = await API.get(`/stats/review/${taskId}/full`);
        if (!data) {
            throw new Error('未找到数据');
        }
        currentReview = data.review;
        currentIssues = data.issues || [];
        currentSummary = data.summary || {};
        activeTab = 'overview';
        renderReviewDetail(content);
    } catch (error) {
        console.error('Load review detail failed:', error);
        content.innerHTML = `
            <div class="error-state">
                <div class="error-icon">❌</div>
                <h3>加载失败</h3>
                <p>${error.message}</p>
                <button class="btn btn-primary" onclick="closeReviewDetail()">关闭</button>
            </div>
        `;
    }
}


// ==================== 渲染函数 ====================

function renderReviewDetail(container) {
    const review = currentReview;
    const summary = currentSummary;

    container.innerHTML = `
        <div class="review-detail">
            <!-- 头部 -->
            <div class="review-detail-header">
                <div class="header-left">
                    <h2>${escapeHtml(review.project_name || '代码审查')}</h2>
                    <div class="review-meta-row">
                        <span class="strategy-badge ${review.strategy}">${review.strategy === 'commit' ? 'Commit' : 'MR'}</span>
                        <span class="status-badge ${getStatusClass(review.status)}">${getStatusText(review.status)}</span>
                        <span class="meta-item">👤 ${escapeHtml(review.author_name || '-')}</span>
                        <span class="meta-item">📅 ${formatDate(review.started_at)}</span>
                    </div>
                </div>
                <div class="header-right">
                    <div class="download-dropdown">
                        <button class="btn-download" onclick="window.toggleDownloadMenu(event)">
                            📥 下载 ▾
                        </button>
                        <div class="download-menu" id="download-menu">
                            <a onclick="window.downloadReport('md')">📄 Markdown</a>
                            <a onclick="window.downloadReport('html')">🌐 HTML</a>
                        </div>
                    </div>
                    <button class="btn-close" onclick="window.closeReviewDetail()">×</button>
                </div>
            </div>

            <!-- 选项卡 -->
            <div class="review-tabs">
                <button class="tab-btn ${activeTab === 'overview' ? 'active' : ''}" 
                        onclick="window.switchReviewTab('overview')">
                    📊 概览
                </button>
                <button class="tab-btn ${activeTab === 'issues' ? 'active' : ''}" 
                        onclick="window.switchReviewTab('issues')">
                    🔍 问题 (${currentIssues.length})
                </button>
                <button class="tab-btn ${activeTab === 'report' ? 'active' : ''}" 
                        onclick="window.switchReviewTab('report')">
                    📄 报告
                </button>
            </div>

            <!-- 内容区域 -->
            <div class="review-tab-content" id="review-tab-content">
                ${renderTabContent()}
            </div>
        </div>
    `;

    initCodeHighlight();
}

function renderTabContent() {
    switch (activeTab) {
        case 'overview':
            return renderOverviewTab();
        case 'issues':
            return renderIssuesTab();
        case 'report':
            return renderReportTab();
        default:
            return renderOverviewTab();
    }
}

function renderOverviewTab() {
    const review = currentReview;
    const summary = currentSummary;

    // 确定评分颜色
    const score = summary.overall_score || 0;
    let scoreClass = 'medium';
    if (score >= 80) scoreClass = 'excellent';
    else if (score >= 60) scoreClass = 'good';
    else if (score < 40) scoreClass = 'poor';

    // 风险等级颜色
    const riskColors = { low: '#22c55e', medium: '#f59e0b', high: '#ef4444' };
    const riskColor = riskColors[summary.risk_level] || riskColors.medium;

    return `
        <div class="overview-tab">
            <!-- 总结卡片 -->
            <div class="summary-cards">
                <div class="summary-card score ${scoreClass}">
                    <div class="card-value">${score.toFixed(0)}</div>
                    <div class="card-label">质量评分</div>
                </div>
                <div class="summary-card verdict">
                    <div class="card-value">${escapeHtml(summary.verdict || '待评估')}</div>
                    <div class="card-label">评审结论</div>
                </div>
                <div class="summary-card risk" style="border-color: ${riskColor}">
                    <div class="card-value" style="color: ${riskColor}">${(summary.risk_level || 'low').toUpperCase()}</div>
                    <div class="card-label">风险等级</div>
                </div>
            </div>

            <!-- 问题统计（使用实时解析的数据） -->
            <div class="issue-stats-row">
                <div class="stat-box total">
                    <div class="stat-value">${currentIssues.length}</div>
                    <div class="stat-label">总问题</div>
                </div>
                <div class="stat-box critical">
                    <div class="stat-value">${currentIssues.filter(i => i.severity === 'critical').length}</div>
                    <div class="stat-label">🔴 严重</div>
                </div>
                <div class="stat-box warning">
                    <div class="stat-value">${currentIssues.filter(i => i.severity === 'warning').length}</div>
                    <div class="stat-label">🟡 警告</div>
                </div>
                <div class="stat-box suggestion">
                    <div class="stat-value">${currentIssues.filter(i => i.severity === 'suggestion').length}</div>
                    <div class="stat-label">🔵 建议</div>
                </div>
            </div>

            <!-- 关键发现 -->
            ${summary.key_findings && summary.key_findings.length ? `
                <div class="findings-section">
                    <h3>🔍 关键发现</h3>
                    <ul class="findings-list">
                        ${summary.key_findings.map(f => `<li>${escapeHtml(f)}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}

            <!-- 改进建议 -->
            ${summary.recommendations && summary.recommendations.length ? `
                <div class="recommendations-section">
                    <h3>💡 改进建议</h3>
                    <ul class="recommendations-list">
                        ${summary.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}

            <!-- 审查元信息 -->
            <div class="review-info-grid">
                <div class="info-item">
                    <span class="info-label">任务ID</span>
                    <span class="info-value">${review.task_id?.slice(0, 8) || '-'}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">分支</span>
                    <span class="info-value">${escapeHtml(review.branch || '-')}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">文件数</span>
                    <span class="info-value">${review.files_count || 0}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">耗时</span>
                    <span class="info-value">${review.processing_time_seconds ? review.processing_time_seconds.toFixed(1) + 's' : '-'}</span>
                </div>
            </div>

            ${renderBatchProgress(review)}
        </div>
    `;
}

// 渲染批次进度
function renderBatchProgress(review) {
    const batchTotal = review.batch_total || 1;
    const batchCurrent = review.batch_current || 0;

    // 如果只有1批，不显示批次信息
    if (batchTotal <= 1 && review.status === 'completed') {
        return '';
    }

    // 解析批次结果
    let batchResults = [];
    if (review.batch_results) {
        try {
            batchResults = JSON.parse(review.batch_results);
        } catch (e) {
            console.warn('解析批次结果失败:', e);
        }
    }

    // 进度百分比
    const progress = batchTotal > 0 ? Math.round((batchCurrent / batchTotal) * 100) : 0;
    const isProcessing = review.status === 'processing';

    return `
        <div class="batch-progress-section">
            <h3>📦 批次执行${isProcessing ? ' (进行中...)' : ''}</h3>
            
            <!-- 进度条 -->
            <div class="batch-progress-bar">
                <div class="progress-track">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
                <span class="progress-text">${batchCurrent} / ${batchTotal} 批次 (${progress}%)</span>
            </div>
            
            <!-- 批次结果列表 -->
            ${batchResults.length > 0 ? `
                <div class="batch-results-list">
                    ${batchResults.map(batch => `
                        <div class="batch-result-item ${batch.status}">
                            <div class="batch-header">
                                <span class="batch-num">${batch.status === 'success' ? '✅' : '❌'} 批次 ${batch.batch}</span>
                                <span class="batch-files">${batch.files_count} 个文件</span>
                            </div>
                            <div class="batch-files-preview">
                                ${batch.files.map(f => `<code>${escapeHtml(f)}</code>`).join(', ')}
                                ${batch.files_count > 3 ? '...' : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        </div>
    `;
}



function renderIssuesTab() {
    if (currentIssues.length === 0) {
        return `
            <div class="empty-issues">
                <div class="empty-icon">✅</div>
                <p>未发现问题，代码质量良好！</p>
            </div>
        `;
    }

    // 筛选器
    const filterHtml = `
        <div class="issues-filter">
            <button class="filter-btn active" data-filter="all" onclick="window.filterIssues('all')">全部 (${currentIssues.length})</button>
            <button class="filter-btn" data-filter="critical" onclick="window.filterIssues('critical')">🔴 严重</button>
            <button class="filter-btn" data-filter="warning" onclick="window.filterIssues('warning')">🟡 警告</button>
            <button class="filter-btn" data-filter="suggestion" onclick="window.filterIssues('suggestion')">🔵 建议</button>
        </div>
    `;

    // 问题列表
    const issuesHtml = currentIssues.map((issue, index) => renderIssueCard(issue, index)).join('');

    return `
        <div class="issues-tab">
            ${filterHtml}
            <div class="issues-list" id="issues-list">
                ${issuesHtml}
            </div>
        </div>
    `;
}

function renderIssueCard(issue, index) {
    const severityIcons = { critical: '🔴', warning: '🟡', suggestion: '🔵', info: 'ℹ️' };
    const severityLabels = { critical: '严重', warning: '警告', suggestion: '建议', info: '信息' };

    const icon = severityIcons[issue.severity] || '•';
    const label = severityLabels[issue.severity] || issue.severity;

    const locationHtml = issue.file_path
        ? `<span class="issue-location">${escapeHtml(issue.file_path)}${issue.line_number ? ':' + issue.line_number : ''}</span>`
        : '';

    return `
        <div class="issue-card ${issue.severity}" data-severity="${issue.severity}">
            <div class="issue-header" onclick="window.toggleIssue(${index})">
                <span class="issue-icon">${icon}</span>
                <span class="issue-badge">${label}</span>
                <span class="issue-title">${escapeHtml(issue.title)}</span>
                ${locationHtml}
                <span class="issue-expand">▼</span>
            </div>
            <div class="issue-body" id="issue-body-${index}" style="display: none;">
                ${issue.description ? `<div class="issue-description">${escapeHtml(issue.description)}</div>` : ''}
                
                ${issue.code_snippet ? `
                    <div class="issue-code">
                        <div class="code-label">问题代码:</div>
                        <pre><code>${escapeHtml(issue.code_snippet)}</code></pre>
                    </div>
                ` : ''}
                
                ${issue.suggestion ? `
                    <div class="issue-suggestion">
                        <div class="suggestion-label">💡 建议修改:</div>
                        <div class="suggestion-content">${escapeHtml(issue.suggestion)}</div>
                    </div>
                ` : ''}
                
                ${issue.category ? `<span class="issue-category">${escapeHtml(issue.category)}</span>` : ''}
            </div>
        </div>
    `;
}

function renderReportTab() {
    const report = currentReview.report || '暂无报告';

    return `
        <div class="report-tab">
            <div class="report-toolbar">
                <button class="btn-small" onclick="window.copyReport()">📋 复制</button>
                <button class="btn-small" onclick="window.downloadReport('md')">📥 下载 Markdown</button>
                <button class="btn-small" onclick="window.downloadReport('html')">📥 下载 HTML</button>
            </div>
            <div class="report-content">
                ${renderMarkdown(report)}
            </div>
        </div>
    `;
}

// ==================== 工具函数 ====================

function renderMarkdown(text) {
    if (!text) return '';

    // 过滤掉 <think>...</think> 标签内容
    let cleaned = text.replace(/<think>[\s\S]*?<\/think>/gi, '');

    // 也过滤非标签格式的 think 块（某些模型输出）
    cleaned = cleaned.replace(/\[think\][\s\S]*?\[\/think\]/gi, '');

    return cleaned
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/^### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^# (.+)$/gm, '<h2>$1</h2>')
        .replace(/\n/g, '<br>');
}

function initCodeHighlight() {
    if (window.hljs) {
        setTimeout(() => {
            document.querySelectorAll('.review-detail pre code').forEach(block => {
                window.hljs.highlightElement(block);
            });
        }, 100);
    }
}

// ==================== 事件处理 ====================

export function switchReviewTab(tab) {
    activeTab = tab;

    // 更新选项卡按钮状态
    document.querySelectorAll('.review-tabs .tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.includes(
            tab === 'overview' ? '概览' : tab === 'issues' ? '问题' : '报告'
        ));
    });

    // 更新内容
    const contentEl = document.getElementById('review-tab-content');
    if (contentEl) {
        contentEl.innerHTML = renderTabContent();
        initCodeHighlight();
    }
}

export function toggleIssue(index) {
    const body = document.getElementById(`issue-body-${index}`);
    if (body) {
        const isHidden = body.style.display === 'none';
        body.style.display = isHidden ? 'block' : 'none';

        // 更新展开图标
        const card = body.parentElement;
        const expand = card.querySelector('.issue-expand');
        if (expand) {
            expand.textContent = isHidden ? '▲' : '▼';
        }
    }
}

export function filterIssues(severity) {
    // 更新按钮状态
    document.querySelectorAll('.issues-filter .filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === severity);
    });

    // 筛选问题
    document.querySelectorAll('.issue-card').forEach(card => {
        if (severity === 'all' || card.dataset.severity === severity) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

export function toggleDownloadMenu(event) {
    event.stopPropagation();
    const menu = document.getElementById('download-menu');
    if (menu) {
        menu.classList.toggle('show');
    }
}

export async function downloadReport(format) {
    if (!currentReview) return;

    const taskId = currentReview.task_id;
    const url = `/api/stats/review/${taskId}/export?format=${format}`;

    // 触发下载
    const link = document.createElement('a');
    link.href = url;
    link.download = `review_${taskId.slice(0, 8)}.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // 关闭下载菜单
    const menu = document.getElementById('download-menu');
    if (menu) menu.classList.remove('show');
}

export function copyReport() {
    if (!currentReview || !currentReview.report) return;

    navigator.clipboard.writeText(currentReview.report).then(() => {
        alert('报告已复制到剪贴板');
    }).catch(() => {
        alert('复制失败，请手动选择复制');
    });
}

export function closeReviewDetail() {
    const modal = document.getElementById('review-modal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
            modal.classList.remove('review-detail-modal');
        }, 300);
    }

    currentReview = null;
    currentIssues = [];
    currentSummary = null;
}

// ==================== 初始化 ====================

export function initReviewDetail() {
    // 绑定全局函数
    window.showReviewDetail = showReviewDetail;
    window.closeReviewDetail = closeReviewDetail;
    window.switchReviewTab = switchReviewTab;
    window.toggleIssue = toggleIssue;
    window.filterIssues = filterIssues;
    window.toggleDownloadMenu = toggleDownloadMenu;
    window.downloadReport = downloadReport;
    window.copyReport = copyReport;

    // 点击外部关闭下载菜单
    document.addEventListener('click', () => {
        const menu = document.getElementById('download-menu');
        if (menu) menu.classList.remove('show');
    });

    // ESC 关闭模态框
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeReviewDetail();
    });
}
