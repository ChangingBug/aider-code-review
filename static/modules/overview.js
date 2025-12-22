/**
 * 概览页面模块
 */

import { API } from './api.js';

let charts = {};

export async function loadOverview() {
    const data = await API.get('/stats/overview');

    if (data) {
        // 更新统计卡片
        const updateText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        updateText('stat-total', data.total_reviews || 0);
        updateText('stat-completed', data.completed_reviews || 0);
        updateText('stat-issues', data.total_issues || 0);
        updateText('stat-critical', data.critical_issues || 0);
        updateText('stat-avg-time', data.avg_processing_time || '--');
        updateText('stat-avg-score', data.avg_quality_score || '--');

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

    if (window.Chart) {
        charts.dailyTrend = new window.Chart(ctx, {
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
}

function updateReviewTypeChart(commits, mrs) {
    const ctx = document.getElementById('chart-review-type');
    if (!ctx) return;

    if (charts.reviewType) {
        charts.reviewType.destroy();
    }

    if (window.Chart) {
        charts.reviewType = new window.Chart(ctx, {
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
}

function updateIssueSeverityChart(critical, warning, suggestion) {
    const ctx = document.getElementById('chart-issue-severity');
    if (!ctx) return;

    if (charts.issueSeverity) {
        charts.issueSeverity.destroy();
    }

    if (window.Chart) {
        charts.issueSeverity = new window.Chart(ctx, {
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
}
