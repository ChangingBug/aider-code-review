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

const pages = ['overview', 'reviews', 'authors', 'projects', 'settings'];
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
        case 'settings':
            await loadSettings();
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

// ==================== 设置页面 ====================

async function loadSettings() {
    const data = await API.get('/settings');
    if (!data) return;

    // 填充表单
    data.forEach(setting => {
        const input = document.querySelector(`[name="${setting.key}"]`);
        if (!input) return;

        if (input.type === 'checkbox') {
            input.checked = setting.value === 'true';
        } else {
            input.value = setting.value || '';
        }
    });

    // 加载轮询数据
    loadPollingData();

    // 根据触发模式显示/隐藏轮询仓库区域
    togglePollingUI();
}

async function saveSettings(e) {
    e.preventDefault();

    const form = document.getElementById('settings-form');
    const statusEl = document.getElementById('settings-status');
    const formData = new FormData(form);

    // 构建设置对象
    const settings = {};

    // 文本输入
    ['git_platform', 'git_server_url', 'git_http_user', 'git_http_password',
        'git_api_url', 'git_token', 'vllm_api_base', 'vllm_api_key', 'vllm_model_name',
        'aider_map_tokens'].forEach(key => {
            settings[key] = formData.get(key) || '';
        });

    // 复选框（checkbox未选中时不会出现在FormData中）
    settings['enable_comment'] = form.querySelector('[name="enable_comment"]').checked ? 'true' : 'false';
    settings['aider_no_repo_map'] = form.querySelector('[name="aider_no_repo_map"]').checked ? 'true' : 'false';

    // 轮询配置
    settings['trigger_mode'] = formData.get('trigger_mode') || 'webhook';
    settings['polling_interval'] = formData.get('polling_interval') || '5';

    // 发送保存请求
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        if (response.ok) {
            statusEl.textContent = '✓ 设置已保存';
            statusEl.className = 'settings-status';
        } else {
            statusEl.textContent = '✗ 保存失败';
            statusEl.className = 'settings-status error';
        }

        // 3秒后清除状态
        setTimeout(() => {
            statusEl.textContent = '';
        }, 3000);
    } catch (error) {
        statusEl.textContent = '✗ 保存失败: ' + error.message;
        statusEl.className = 'settings-status error';
    }
}

// 绑定设置表单提交
document.getElementById('settings-form')?.addEventListener('submit', saveSettings);

// ==================== 连接测试 ====================

async function testGitConnection() {
    const resultEl = document.getElementById('git-test-result');
    resultEl.className = 'test-result loading';
    resultEl.textContent = '⏳ 测试中...';

    try {
        const response = await fetch('/api/test/git', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            resultEl.className = 'test-result success';
            // 显示所有检查结果
            const checks = data.details.checks || [];
            resultEl.textContent = checks.join(' | ');
        } else {
            resultEl.className = 'test-result error';
            const checks = data.details.checks || [data.message];
            resultEl.textContent = checks.join(' | ');
        }
    } catch (error) {
        resultEl.className = 'test-result error';
        resultEl.textContent = `✗ 请求失败: ${error.message}`;
    }
}

async function testVllmConnection() {
    const resultEl = document.getElementById('vllm-test-result');
    resultEl.className = 'test-result loading';
    resultEl.textContent = '⏳ 正在与模型对话...';

    try {
        const response = await fetch('/api/test/vllm', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            resultEl.className = 'test-result success';
            const reply = data.details.reply || '';
            resultEl.textContent = `✓ ${data.message} (${data.details.response_time}) - "${reply}"`;
        } else {
            resultEl.className = 'test-result error';
            resultEl.textContent = `✗ ${data.message}`;
        }
    } catch (error) {
        resultEl.className = 'test-result error';
        resultEl.textContent = `✗ 请求失败: ${error.message}`;
    }
}

async function testAider() {
    const resultEl = document.getElementById('aider-test-result');
    resultEl.className = 'test-result loading';
    resultEl.textContent = '⏳ 测试中...';

    try {
        const response = await fetch('/api/test/aider', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            resultEl.className = 'test-result success';
            resultEl.textContent = `✓ ${data.message} (v${data.details.version})`;
        } else {
            resultEl.className = 'test-result error';
            // 显示更详细的错误信息
            let errorDetail = data.details?.error || data.details?.hint || '';
            if (errorDetail && errorDetail.length > 50) {
                errorDetail = errorDetail.substring(0, 50) + '...';
            }
            resultEl.textContent = `✗ ${data.message}${errorDetail ? ': ' + errorDetail : ''}`;
        }
    } catch (error) {
        resultEl.className = 'test-result error';
        resultEl.textContent = `✗ 请求失败: ${error.message}`;
    }
}

// ==================== 轮询管理 ====================

// 加载轮询状态和仓库列表
async function loadPollingData() {
    try {
        // 加载状态
        const statusRes = await fetch('/api/polling/status');
        const status = await statusRes.json();
        updatePollingStatusUI(status);

        // 加载仓库列表
        const reposRes = await fetch('/api/polling/repos');
        const data = await reposRes.json();
        renderReposList(data.repos || []);
    } catch (error) {
        console.error('加载轮询数据失败:', error);
    }
}

// 更新轮询状态UI
function updatePollingStatusUI(status) {
    const btn = document.getElementById('polling-toggle-btn');
    const statusEl = document.getElementById('polling-status');

    if (status.running) {
        btn.textContent = '⏹️ 停止轮询';
        btn.classList.add('btn-danger');
        statusEl.className = 'test-result success';
        statusEl.textContent = `✓ 运行中 (${status.enabled_repos}/${status.repos_count} 个仓库, 每${status.interval}分钟)`;
    } else {
        btn.textContent = '▶️ 启动轮询';
        btn.classList.remove('btn-danger');
        statusEl.className = 'test-result';
        statusEl.textContent = status.repos_count > 0 ? `已配置 ${status.repos_count} 个仓库` : '';
    }
}

// 渲染仓库列表
function renderReposList(repos) {
    const container = document.getElementById('repos-list');

    if (repos.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="text-align: center; padding: 30px; color: var(--text-muted);">
                <p>暂无监控仓库</p>
                <p style="font-size: 12px;">点击"添加仓库"开始配置</p>
            </div>
        `;
        return;
    }

    container.innerHTML = repos.map(repo => `
        <div class="repo-item" data-id="${repo.id}">
            <div class="repo-info">
                <div class="repo-name">${repo.name}</div>
                <div class="repo-url">${repo.url}</div>
                <div class="repo-meta">
                    分支: ${repo.branch} | 
                    ${repo.poll_commits ? '✓提交' : ''} 
                    ${repo.poll_mrs ? '✓MR' : ''} |
                    ${repo.enabled ? '🟢启用' : '🔴禁用'}
                </div>
            </div>
            <div class="repo-actions">
                <button class="btn btn-test btn-sm" onclick="toggleRepoEnabled('${repo.id}', ${!repo.enabled})">
                    ${repo.enabled ? '禁用' : '启用'}
                </button>
                <button class="btn btn-test btn-sm btn-danger" onclick="deleteRepo('${repo.id}')">
                    删除
                </button>
            </div>
        </div>
    `).join('');
}

// 显示添加仓库模态框
function showAddRepoModal() {
    document.getElementById('add-repo-modal').classList.add('active');
}

// 关闭添加仓库模态框
function closeAddRepoModal() {
    document.getElementById('add-repo-modal').classList.remove('active');
    // 清空表单
    document.getElementById('new-repo-name').value = '';
    document.getElementById('new-repo-url').value = '';
    document.getElementById('new-repo-branch').value = 'main';
    document.getElementById('new-repo-commits').checked = true;
    document.getElementById('new-repo-mrs').checked = false;
}

// 切换鉴权方式显示
function toggleAuthFields() {
    const authType = document.getElementById('new-repo-auth-type').value;
    document.getElementById('http-auth-fields').style.display = authType === 'http_basic' ? 'grid' : 'none';
    document.getElementById('token-auth-fields').style.display = authType === 'token' ? 'block' : 'none';
}

// 平台切换时重新推断API地址
function onPlatformChange() {
    const url = document.getElementById('new-repo-url').value.trim();
    if (url) {
        const platform = document.getElementById('new-repo-platform').value;
        const apiUrl = inferApiUrl(url, platform);
        if (apiUrl) {
            document.getElementById('new-repo-api-url').value = apiUrl;
        }
    }
}

// 评论开关与API地址字段联动
function toggleApiUrlField() {
    const enableComment = document.getElementById('new-repo-enable-comment').checked;
    document.getElementById('api-url-field').style.display = enableComment ? 'block' : 'none';
}

// 从仓库URL推断API地址
function inferApiUrl(repoUrl, platform) {
    try {
        const url = new URL(repoUrl);
        const baseUrl = `${url.protocol}//${url.host}`;

        switch (platform) {
            case 'gitlab':
                return `${baseUrl}/api/v4`;
            case 'gitea':
                return `${baseUrl}/api/v1`;
            case 'github':
                // GitHub Enterprise使用/api/v3，公共GitHub使用api.github.com
                if (url.host === 'github.com') {
                    return 'https://api.github.com';
                }
                return `${baseUrl}/api/v3`;
            default:
                return `${baseUrl}/api/v4`;
        }
    } catch (e) {
        return '';
    }
}

// URL变化时自动解析仓库名称和API地址
let urlParseTimer = null;
function onRepoUrlChange() {
    const url = document.getElementById('new-repo-url').value.trim();
    if (!url) return;

    // 自动推断API地址
    const platform = document.getElementById('new-repo-platform').value;
    const apiUrl = inferApiUrl(url, platform);
    if (apiUrl) {
        document.getElementById('new-repo-api-url').value = apiUrl;
    }

    // 防抖解析仓库名称
    clearTimeout(urlParseTimer);
    urlParseTimer = setTimeout(async () => {
        try {
            const response = await fetch('/api/polling/parse-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            const data = await response.json();
            if (data.name) {
                document.getElementById('new-repo-name').value = data.name;
            }
        } catch (e) {
            console.error('解析URL失败:', e);
        }
    }, 500);
}

// 更新分支输入框
function updateBranchInput() {
    const select = document.getElementById('new-repo-branch-select');
    const input = document.getElementById('new-repo-branch');
    if (select.value) {
        input.value = select.value;
    }
}

// 加载分支列表
async function loadBranches() {
    const resultEl = document.getElementById('add-repo-result');
    const btn = document.getElementById('load-branches-btn');
    const select = document.getElementById('new-repo-branch-select');

    const url = document.getElementById('new-repo-url').value.trim();
    const platform = document.getElementById('new-repo-platform').value;
    const authType = document.getElementById('new-repo-auth-type').value;
    const token = document.getElementById('new-repo-token').value;
    const httpUser = document.getElementById('new-repo-http-user').value;
    const httpPassword = document.getElementById('new-repo-http-password').value;
    const apiUrl = document.getElementById('new-repo-api-url').value.trim();

    if (!url) {
        resultEl.className = 'test-result error';
        resultEl.textContent = '请先输入仓库URL';
        return;
    }

    if (!apiUrl) {
        resultEl.className = 'test-result error';
        resultEl.textContent = '请先输入API地址';
        return;
    }

    btn.disabled = true;
    btn.textContent = '加载中...';
    resultEl.className = 'test-result loading';
    resultEl.textContent = '⏳ 正在获取分支列表...';

    try {
        const response = await fetch('/api/polling/branches', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url, platform, auth_type: authType,
                token, http_user: httpUser, http_password: httpPassword,
                api_url: apiUrl
            })
        });
        const data = await response.json();

        select.innerHTML = '<option value="">-- 选择分支 --</option>';
        if (data.branches && data.branches.length > 0) {
            data.branches.forEach(branch => {
                const option = document.createElement('option');
                option.value = branch;
                option.textContent = branch;
                select.appendChild(option);
            });
            resultEl.className = 'test-result success';
            resultEl.textContent = `✓ 加载了 ${data.branches.length} 个分支`;
        } else {
            resultEl.className = 'test-result error';
            resultEl.textContent = '未找到分支，请检查URL和认证信息';
        }
    } catch (e) {
        resultEl.className = 'test-result error';
        resultEl.textContent = `加载失败: ${e.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 加载';
    }
}

// 添加仓库
async function addRepo() {
    const resultEl = document.getElementById('add-repo-result');

    const name = document.getElementById('new-repo-name').value.trim();
    const url = document.getElementById('new-repo-url').value.trim();
    const branch = document.getElementById('new-repo-branch').value.trim() || 'main';
    const platform = document.getElementById('new-repo-platform').value;
    const authType = document.getElementById('new-repo-auth-type').value;
    const token = document.getElementById('new-repo-token').value;
    const httpUser = document.getElementById('new-repo-http-user').value;
    const httpPassword = document.getElementById('new-repo-http-password').value;
    const apiUrl = document.getElementById('new-repo-api-url').value.trim();
    const localPath = document.getElementById('new-repo-local-path').value.trim();
    const effectiveTime = document.getElementById('new-repo-effective-time').value;
    const pollCommits = document.getElementById('new-repo-commits').checked;
    const pollMrs = document.getElementById('new-repo-mrs').checked;
    const enableComment = document.getElementById('new-repo-enable-comment').checked;

    if (!url) {
        resultEl.className = 'test-result error';
        resultEl.textContent = '请输入仓库URL';
        return;
    }

    if (!apiUrl) {
        resultEl.className = 'test-result error';
        resultEl.textContent = '请输入API地址';
        return;
    }

    resultEl.className = 'test-result loading';
    resultEl.textContent = '⏳ 正在添加仓库...';

    try {
        // 1. 添加仓库
        const response = await fetch('/api/polling/repos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name || url.split('/').pop().replace('.git', ''),
                url, branch, platform,
                auth_type: authType,
                token, http_user: httpUser, http_password: httpPassword,
                api_url: apiUrl,
                local_path: localPath,
                effective_time: effectiveTime,
                poll_commits: pollCommits,
                poll_mrs: pollMrs,
                enable_comment: enableComment
            })
        });

        if (!response.ok) {
            const error = await response.json();
            resultEl.className = 'test-result error';
            resultEl.textContent = '添加失败: ' + (error.detail || '未知错误');
            return;
        }

        const repoData = await response.json();
        const repoId = repoData.repo?.id;

        resultEl.textContent = '⏳ 仓库已添加，正在克隆代码...';

        // 2. 克隆仓库
        if (repoId) {
            const cloneResponse = await fetch(`/api/polling/repos/${repoId}/clone`, {
                method: 'POST'
            });
            const cloneResult = await cloneResponse.json();

            if (cloneResult.success) {
                resultEl.className = 'test-result success';
                resultEl.textContent = `✓ ${cloneResult.message}`;

                // 延迟关闭
                setTimeout(() => {
                    closeAddRepoModal();
                    loadPollingData();
                }, 1500);
            } else {
                resultEl.className = 'test-result error';
                resultEl.textContent = `仓库已添加，但克隆失败: ${cloneResult.message}`;
                loadPollingData();
            }
        }
    } catch (error) {
        resultEl.className = 'test-result error';
        resultEl.textContent = '添加失败: ' + error.message;
    }
}

// 删除仓库
async function deleteRepo(repoId) {
    if (!confirm('确定要删除这个仓库吗？')) return;

    try {
        const response = await fetch(`/api/polling/repos/${repoId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadPollingData();
        }
    } catch (error) {
        console.error('删除失败:', error);
    }
}

// 切换仓库启用状态
async function toggleRepoEnabled(repoId, enabled) {
    try {
        const response = await fetch(`/api/polling/repos/${repoId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });

        if (response.ok) {
            loadPollingData();
        }
    } catch (error) {
        console.error('更新失败:', error);
    }
}

// 切换轮询开关
async function togglePolling() {
    const btn = document.getElementById('polling-toggle-btn');
    const isRunning = btn.textContent.includes('停止');

    try {
        const endpoint = isRunning ? '/api/polling/stop' : '/api/polling/start';
        const response = await fetch(endpoint, { method: 'POST' });

        if (response.ok) {
            // 重新加载状态
            setTimeout(loadPollingData, 500);
        }
    } catch (error) {
        console.error('操作失败:', error);
    }
}

// 切换轮询UI显示
function togglePollingUI() {
    const mode = document.querySelector('[name="trigger_mode"]').value;
    const section = document.getElementById('polling-repos-section');
    section.style.display = mode === 'polling' ? 'block' : 'none';
}

// ==================== 初始化 ====================

let pollingRefreshInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    navigateTo('overview');

    // 每30秒自动刷新（设置页面除外）
    setInterval(() => {
        if (currentPage !== 'settings') {
            loadPageData(currentPage);
        }
    }, 30000);

    // 在设置页面，每10秒刷新轮询状态
    setInterval(() => {
        if (currentPage === 'settings') {
            loadPollingData();
        }
    }, 10000);
});
