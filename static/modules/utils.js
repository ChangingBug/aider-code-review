/**
 * 工具函数模块
 */

export function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });
}

export function formatTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
    return formatDate(isoString);
}

export function getInitials(name) {
    if (!name) return '?';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
}

export function getStatusClass(status) {
    const statusMap = {
        'completed': 'success',
        'processing': 'pending',
        'failed': 'error'
    };
    return statusMap[status] || 'pending';
}

export function getStatusText(status) {
    const textMap = {
        'completed': '已完成',
        'processing': '处理中',
        'failed': '失败'
    };
    return textMap[status] || status;
}

export function renderScore(score) {
    if (score === null || score === undefined) return '<span class="score">-</span>';
    const scoreNum = parseFloat(score);
    let className = 'medium';
    if (scoreNum >= 80) className = 'excellent';
    else if (scoreNum >= 60) className = 'good';
    else if (scoreNum < 40) className = 'poor';
    return `<span class="score ${className}">${scoreNum.toFixed(0)}</span>`;
}

export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
