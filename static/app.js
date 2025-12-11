/**
 * Aider Code Review Dashboard - 前端应用
 */

// ==================== API调用 ====================

const API = {
    async get(endpoint) {
        try {
            const response = await fetch(`/api${endpoint}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`API Error: ${endpoint}`, error);
            return null;
        }
    }
};

// ==================== 页面路由 ====================

const pages = ['overview', 'reviews', 'authors', 'projects'];
let currentPage = 'overview';
let charts = {};

function navigateTo(page) {
    if (!pages.includes(page)) return;
    
    // 更新导航状态
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.page === page);
    });
    
    // 切换页面显示
    pages.forEach(p => {
        const el = document.getElementById(`page-${p}`);
        if (el) el.style.display = p === page ? 'block' : 'none';
    });
    
    currentPage = page;
    loadPageData(page);
}

// 绑定导航事件
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        navigateTo(link.dataset.page);
    });
});

// ==================== 数据加载 ====================

async function loadPageData(page) {
    switch (page) {
        case 'overview':
            await loadOverview();
            break;
        case 'reviews':
            await loadReviews();
            break;
        case 'authors':
            await loadAuthors();
            break;
        case 'projects':
            await loadProjects();
            break;
    }
}

// ==================== 概览页面 ====================

async function loadOverview() {
    const data = await API.get('/stats/overview');
    
    if (data) {
        // 更新统计卡片
        document.getElementById('stat-total').textContent = data.total_reviews || 0;
        document.getElementById('stat-completed').textContent = data.completed_reviews || 0;
        document.getElementById('stat-issues').textContent = data.total_issues || 0;
        document.getElementById('stat-critical').textContent = data.critical_issues || 0;
        document.getElementById('stat-avg-time').textContent = data.avg_processing_time || '--';
        document.getElementById('stat-avg-score').textContent = data.avg_quality_score || '--';
        
        // 更新审查类型饼图
        updateReviewTypeChart(data.commit_reviews, data.mr_reviews);
        
        // 更新问题严重程度饼图
        updateIssueSeverityChart(
            data.critical_issues,
            data.warning_issues,
            data.suggestion_issues
        );
    }
    
    // 加载每日趋势
    const trend = await API.get('/stats/daily-trend?days=30');
    if (trend) {
        updateDailyTrendChart(trend);
    }
}

function updateDailyTrendChart(data) {
    const ctx = document.getElementById('chart-daily-trend');
    if (!ctx) return;
    
    if (charts.dailyTrend) {
        charts.dailyTrend.destroy();
    }
    
    const labels = data.map(d => d.date);
    const counts = data.map(d => d.count);
    const issues = data.map(d => d.issues);
    
    charts.dailyTrend = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '审查次数',
                    data: counts,
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    fill: true,
                    tension: 0.4
                },
                {
                    label: '发现问题',
                    data: issues,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    fill: true,
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8' }
                }
            },
            scales: {
                x: {
                    grid: { color: '#334155' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    grid: { color: '#334155' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
}

function updateReviewTypeChart(commits, mrs) {
    const ctx = document.getElementById('chart-review-type');
    if (!ctx) return;
    
    if (charts.reviewType) {
        charts.reviewType.destroy();
    }
    
    charts.reviewType = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Commit审查', 'MR审查'],
            datasets: [{
                data: [commits || 0, mrs || 0],
                backgroundColor: ['#6366f1', '#10b981'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8' }
                }
            }
        }
    });
}

function updateIssueSeverityChart(critical, warning, suggestion) {
    const ctx = document.getElementById('chart-issue-severity');
    if (!ctx) return;
    
    if (charts.issueSeverity) {
        charts.issueSeverity.destroy();
    }
    
    charts.issueSeverity = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['严重', '警告', '建议'],
            datasets: [{
                data: [critical || 0, warning || 0, suggestion || 0],
                backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8' }
                }
            }
        }
    });
}

// ==================== 审查记录页面 ====================

async function loadReviews() {
    const data = await API.get('/stats/reviews?limit=50');
    const tbody = document.getElementById('reviews-table-body');
    
    if (!data || !data.reviews || data.reviews.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7">
                    <div class="empty-state">
                        <div class="empty-icon">📭</div>
                        <div class="empty-title">暂无审查记录</div>
                        <div class="empty-text">等待Git平台触发Webhook</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = data.reviews.map(review => `
        <tr onclick="showReviewDetail('${review.task_id}')" style="cursor: pointer;">
            <td>${formatDate(review.created_at)}</td>
            <td>${review.project_name || '-'}</td>
            <td>
                <div class="author-info">
                    <div class="author-avatar">${getInitials(review.author_name)}</div>
                    <div>
                        <div class="author-name">${review.author_name || 'Unknown'}</div>
                    </div>
                </div>
            </td>
            <td><span class="badge ${review.strategy === 'commit' ? 'info' : 'success'}">${review.strategy === 'commit' ? 'Commit' : 'MR'}</span></td>
            <td><span class="badge ${getStatusClass(review.status)}">${getStatusText(review.status)}</span></td>
            <td>${review.issues_count || 0}</td>
            <td>${renderScore(review.quality_score)}</td>
        </tr>
    `).join('');
}

// ==================== 提交人统计页面 ====================

async function loadAuthors() {
    const data = await API.get('/stats/authors?limit=20');
    const tbody = document.getElementById('authors-table-body');
    
    if (!data || data.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="empty-state">
                        <div class="empty-icon">👥</div>
                        <div class="empty-title">暂无数据</div>
                        <div class="empty-text">等待审查数据积累</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = data.map(author => `
        <tr>
            <td>
                <div class="author-info">
                    <div class="author-avatar">${getInitials(author.author_name)}</div>
                    <div>
                        <div class="author-name">${author.author_name}</div>
                        <div class="author-email">${author.author_email || ''}</div>
                    </div>
                </div>
            </td>
            <td>${author.review_count}</td>
            <td>${author.total_issues}</td>
            <td><span class="badge critical">${author.critical_issues}</span></td>
            <td>${renderScore(author.avg_score)}</td>
            <td>${author.issue_rate}</td>
        </tr>
    `).join('');
    
    // 更新贡献对比图表
    updateAuthorContributionChart(data);
}

function updateAuthorContributionChart(data) {
    const ctx = document.getElementById('chart-author-contribution');
    if (!ctx) return;
    
    if (charts.authorContribution) {
        charts.authorContribution.destroy();
    }
    
    const top10 = data.slice(0, 10);
    
    charts.authorContribution = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: top10.map(a => a.author_name),
            datasets: [
                {
                    label: '审查次数',
                    data: top10.map(a => a.review_count),
                    backgroundColor: '#6366f1'
                },
                {
                    label: '问题数',
                    data: top10.map(a => a.total_issues),
                    backgroundColor: '#f59e0b'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8' }
                }
            },
            scales: {
                x: {
                    grid: { color: '#334155' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    grid: { color: '#334155' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
}

// ==================== 项目统计页面 ====================

async function loadProjects() {
    const data = await API.get('/stats/projects?limit=20');
    const tbody = document.getElementById('projects-table-body');
    
    if (!data || data.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="empty-state">
                        <div class="empty-icon">📁</div>
                        <div class="empty-title">暂无项目数据</div>
                        <div class="empty-text">等待审查数据积累</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = data.map(project => `
        <tr>
            <td><strong>${project.project_name}</strong></td>
            <td><span class="badge info">${project.platform}</span></td>
            <td>${project.review_count}</td>
            <td>${project.total_issues}</td>
            <td>${project.contributor_count}</td>
            <td>${renderScore(project.avg_score)}</td>
        </tr>
    `).join('');
}

// ==================== 审查详情模态框 ====================

async function showReviewDetail(taskId) {
    const modal = document.getElementById('review-modal');
    const body = document.getElementById('review-modal-body');
    
    modal.classList.add('active');
    body.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    
    const data = await API.get(`/stats/review/${taskId}`);
    
    if (!data) {
        body.innerHTML = '<div class="empty-state"><div class="empty-title">加载失败</div></div>';
        return;
    }
    
    body.innerHTML = `
        <div style="margin-bottom: 20px;">
            <h4 style="margin-bottom: 12px;">基本信息</h4>
            <table class="data-table" style="font-size: 14px;">
                <tr><td style="width: 120px; color: var(--text-secondary);">任务ID</td><td>${data.task_id}</td></tr>
                <tr><td style="color: var(--text-secondary);">项目</td><td>${data.project_name || '-'}</td></tr>
                <tr><td style="color: var(--text-secondary);">提交人</td><td>${data.author_name || '-'}</td></tr>
                <tr><td style="color: var(--text-secondary);">分支</td><td>${data.branch || '-'}</td></tr>
                <tr><td style="color: var(--text-secondary);">审查类型</td><td>${data.strategy === 'commit' ? 'Commit审查' : 'MR审查'}</td></tr>
                <tr><td style="color: var(--text-secondary);">状态</td><td><span class="badge ${getStatusClass(data.status)}">${getStatusText(data.status)}</span></td></tr>
                <tr><td style="color: var(--text-secondary);">处理时间</td><td>${data.processing_time_seconds ? data.processing_time_seconds.toFixed(2) + '秒' : '-'}</td></tr>
            </table>
        </div>
        
        <div style="margin-bottom: 20px;">
            <h4 style="margin-bottom: 12px;">问题统计</h4>
            <div style="display: flex; gap: 16px;">
                <div><span class="badge critical">严重: ${data.critical_count || 0}</span></div>
                <div><span class="badge warning">警告: ${data.warning_count || 0}</span></div>
                <div><span class="badge suggestion">建议: ${data.suggestion_count || 0}</span></div>
            </div>
        </div>
        
        ${data.report ? `
        <div>
            <h4 style="margin-bottom: 12px;">审查报告</h4>
            <div style="background: var(--bg-primary); padding: 16px; border-radius: 8px; max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 13px; white-space: pre-wrap;">
${escapeHtml(data.report)}
            </div>
        </div>
        ` : ''}
    `;
}

function closeModal() {
    document.getElementById('review-modal').classList.remove('active');
}

// 点击遮罩关闭
document.getElementById('review-modal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        closeModal();
    }
});

// ESC键关闭
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// ==================== 工具函数 ====================

function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function getInitials(name) {
    if (!name) return '?';
    return name.substring(0, 2).toUpperCase();
}

function getStatusClass(status) {
    const classes = {
        'completed': 'success',
        'processing': 'warning',
        'pending': 'pending',
        'failed': 'critical'
    };
    return classes[status] || 'pending';
}

function getStatusText(status) {
    const texts = {
        'completed': '已完成',
        'processing': '处理中',
        'pending': '待处理',
        'failed': '失败'
    };
    return texts[status] || status;
}

function renderScore(score) {
    if (score === null || score === undefined) return '-';
    const scoreNum = parseFloat(score);
    let className = 'fair';
    if (scoreNum >= 80) className = 'excellent';
    else if (scoreNum >= 60) className = 'good';
    else if (scoreNum < 40) className = 'poor';
    
    return `<span class="score ${className}">${scoreNum.toFixed(0)}</span>`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    navigateTo('overview');
    
    // 每30秒自动刷新
    setInterval(() => {
        loadPageData(currentPage);
    }, 30000);
});
