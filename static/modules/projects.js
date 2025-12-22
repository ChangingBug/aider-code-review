/**
 * 项目统计页面模块
 */

import { API } from './api.js';
import { renderScore } from './utils.js';

export async function loadProjects() {
    const data = await API.get('/stats/projects?limit=20');
    const tbody = document.getElementById('projects-table-body');
    if (!tbody) return;

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
            <td><strong>${project.project_name || '-'}</strong></td>
            <td><span class="badge info">${project.platform || '-'}</span></td>
            <td>${project.review_count}</td>
            <td>${project.total_issues}</td>
            <td>${project.contributor_count}</td>
            <td>${renderScore(project.avg_score)}</td>
        </tr>
    `).join('');
}
