/**
 * 提交人统计页面模块
 */

import { API } from './api.js';
import { getInitials, renderScore } from './utils.js';

let charts = {};

export async function loadAuthors() {
    const data = await API.get('/stats/authors?limit=20');
    const tbody = document.getElementById('authors-table-body');
    if (!tbody) return;

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
        // 清空图表
        updateAuthorContributionChart([]);
        return;
    }

    tbody.innerHTML = data.map(author => `
        <tr>
            <td>
                <div class="author-info">
                    <div class="author-avatar">${getInitials(author.author_name)}</div>
                    <div>
                        <div class="author-name">${author.author_name || 'Unknown'}</div>
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

    if (!data || data.length === 0) return;

    const top10 = data.slice(0, 10);

    if (window.Chart) {
        charts.authorContribution = new window.Chart(ctx, {
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
}
