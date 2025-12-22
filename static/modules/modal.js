/**
 * 模态框模块
 */

import { API } from './api.js';
import { formatDate, getStatusClass, getStatusText, escapeHtml } from './utils.js';

export async function showReviewDetail(taskId) {
    const modal = document.getElementById('review-modal');
    const content = document.getElementById('review-modal-content');

    if (!modal || !content) return;

    content.innerHTML = '<div class="loading">加载中...</div>';
    modal.style.display = 'flex';

    const review = await API.get(`/stats/review/${taskId}`);

    if (!review) {
        content.innerHTML = '<div class="error">加载失败</div>';
        return;
    }

    content.innerHTML = `
        <div class="modal-header">
            <h3>${escapeHtml(review.project_name || '-')}</h3>
            <button class="close-btn" onclick="window.closeModal()">×</button>
        </div>
        <div class="modal-body">
            <div class="review-meta">
                <span class="strategy-badge ${review.strategy}">${review.strategy === 'commit' ? 'Commit' : 'MR'}</span>
                <span class="status-badge ${getStatusClass(review.status)}">${getStatusText(review.status)}</span>
                <span>作者: ${escapeHtml(review.author_name || '-')}</span>
                <span>时间: ${formatDate(review.started_at)}</span>
            </div>
            <div class="review-stats">
                <div class="stat-item">
                    <span class="label">问题数</span>
                    <span class="value">${review.issues_count || 0}</span>
                </div>
                <div class="stat-item critical">
                    <span class="label">严重</span>
                    <span class="value">${review.critical_count || 0}</span>
                </div>
                <div class="stat-item warning">
                    <span class="label">警告</span>
                    <span class="value">${review.warning_count || 0}</span>
                </div>
                <div class="stat-item suggestion">
                    <span class="label">建议</span>
                    <span class="value">${review.suggestion_count || 0}</span>
                </div>
            </div>
            <div class="review-report">
                <h4>审查报告</h4>
                <div class="report-content">${renderMarkdown(review.report || '暂无报告')}</div>
            </div>
        </div>
    `;

    initCodeHighlight();
}

function renderMarkdown(text) {
    if (!text) return '';

    // 简单的 Markdown 渲染
    return text
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

function initCodeHighlight() {
    if (window.hljs) {
        document.querySelectorAll('pre code').forEach(block => {
            window.hljs.highlightElement(block);
        });
    }
}

export function closeModal() {
    const modal = document.getElementById('review-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// 初始化模态框事件
export function initModal() {
    const modal = document.getElementById('review-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay')) {
                closeModal();
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });

    // 绑定全局函数
    window.closeModal = closeModal;
}
