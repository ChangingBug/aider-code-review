/**
 * 审查记录页面模块（增强版）
 * 支持搜索、过滤、排序、删除和列筛选
 */

import { API } from './api.js';
import { formatDate, getStatusClass, getStatusText, renderScore, escapeHtml } from './utils.js';
import { showReviewDetail } from './review-detail.js';

let currentSearch = '';
let currentFilters = {};
let currentSort = { field: 'created_at', order: 'desc' };
let hiddenColumns = new Set();

export async function loadReviews() {
    const params = new URLSearchParams({ limit: '50' });

    // 参数构建
    if (currentSearch) params.append('search', currentSearch);
    if (currentFilters.author) params.append('author', currentFilters.author);
    if (currentFilters.status) params.append('status', currentFilters.status);
    if (currentFilters.strategy) params.append('strategy', currentFilters.strategy);

    // 排序参数
    params.append('sort_by', currentSort.field);
    params.append('order', currentSort.order);

    try {
        const data = await API.get(`/stats/reviews?${params.toString()}`);
        if (!data || !data.reviews) return;

        renderReviewsTable(data.reviews, data.total);
        updateSortIcons();
        applyColumnVisibility();
    } catch (error) {
        console.error('加载审查记录失败:', error);
    }
}

function renderReviewsTable(reviews, total) {
    const container = document.getElementById('reviews-table-body');
    if (!container) return;

    if (reviews.length === 0) {
        // 计算可见列数 (总列数 - 隐藏列数)
        const totalCols = 8;
        const visibleCols = totalCols - hiddenColumns.size;

        container.innerHTML = `
            <tr>
                <td colspan="${visibleCols}" class="empty-row">
                    <div class="empty-message">暂无审查记录</div>
                </td>
            </tr>
        `;
        document.getElementById('reviews-total').textContent = '共 0 条记录';
        return;
    }

    container.innerHTML = reviews.map(review => `
        <tr class="review-row" data-task-id="${review.task_id}">
            <td class="col-project">
                <div class="project-cell">
                    <span class="project-name">${escapeHtml(review.project_name || '-')}</span>
                    <span class="task-id">${review.task_id?.slice(0, 8) || '-'}</span>
                </div>
            </td>
            <td class="col-strategy">
                <span class="strategy-badge ${review.strategy}">${review.strategy === 'commit' ? 'Commit' : 'MR'}</span>
            </td>
            <td class="col-author">${escapeHtml(review.author_name || '-')}</td>
            <td class="col-status">
                <span class="status-badge ${getStatusClass(review.status)}">${getStatusText(review.status)}</span>
            </td>
            <td class="col-issues">${review.issues_count || 0}</td>
            <td class="col-score">${renderScore(review.quality_score)}</td>
            <td class="col-time">${formatDate(review.started_at)}</td>
            <td class="col-actions actions-cell">
                <button class="btn-icon" onclick="event.stopPropagation(); window.showReviewDetail('${review.task_id}')" title="查看详情">👁</button>
                <button class="btn-icon danger" onclick="event.stopPropagation(); window.deleteReview('${review.task_id}')" title="删除">🗑</button>
            </td>
        </tr>
    `).join('');

    // 绑定行点击事件
    container.querySelectorAll('.review-row').forEach(row => {
        row.addEventListener('click', () => {
            const taskId = row.dataset.taskId;
            if (taskId) showReviewDetail(taskId);
        });
    });

    // 更新总数
    const totalEl = document.getElementById('reviews-total');
    if (totalEl) totalEl.textContent = `共 ${total} 条记录`;
}

// ==================== 排序功能 ====================

export function sortReviews(field) {
    if (currentSort.field === field) {
        // 切换排序方向
        currentSort.order = currentSort.order === 'desc' ? 'asc' : 'desc';
    } else {
        // 新字段默认降序
        currentSort.field = field;
        currentSort.order = 'desc';
    }
    loadReviews();
}

function updateSortIcons() {
    document.querySelectorAll('th.sortable').forEach(th => {
        // 清除旧状态
        th.classList.remove('sort-asc', 'sort-desc');
        const icon = th.querySelector('.sort-icon');
        if (icon) icon.textContent = '↕';

        // 设置新状态
        if (th.onclick && th.onclick.toString().includes(currentSort.field)) {
            th.classList.add(currentSort.order === 'asc' ? 'sort-asc' : 'sort-desc');
            if (icon) icon.textContent = currentSort.order === 'asc' ? '↑' : '↓';
        }
    });
}

// ==================== 列筛选功能 ====================

export function toggleColumnMenu() {
    const menu = document.getElementById('column-menu');
    if (menu) menu.classList.toggle('show');
}

export function toggleColumn(colName) {
    const checkbox = document.querySelector(`#column-menu input[data-col="${colName}"]`);
    if (!checkbox) return;

    if (checkbox.checked) {
        hiddenColumns.delete(colName);
    } else {
        hiddenColumns.add(colName);
    }

    applyColumnVisibility();
}

function applyColumnVisibility() {
    // 处理表头
    document.querySelectorAll('th').forEach(th => {
        const classList = th.className.split(' ');
        const colClass = classList.find(c => c.startsWith('col-'));
        if (colClass) {
            const colName = colClass.replace('col-', '');
            if (colName !== 'actions') { // 操作列始终显示
                th.style.display = hiddenColumns.has(colName) ? 'none' : '';
            }
        }
    });

    // 处理数据行
    document.querySelectorAll('td').forEach(td => {
        const classList = td.className.split(' ');
        const colClass = classList.find(c => c.startsWith('col-'));
        if (colClass) {
            const colName = colClass.replace('col-', '');
            if (colName !== 'actions') {
                td.style.display = hiddenColumns.has(colName) ? 'none' : '';
            }
        }
    });
}

// ==================== 其他功能 ====================

export async function deleteReview(taskId) {
    if (!confirm('确定要删除此审查记录吗？此操作不可恢复。')) return;

    try {
        const result = await API.delete(`/stats/review/${taskId}`);
        if (result && result.status === 'deleted') {
            loadReviews();
        } else {
            alert('删除失败');
        }
    } catch (error) {
        console.error('删除失败:', error);
        alert('删除请求失败');
    }
}

export function searchReviews(keyword) {
    currentSearch = keyword;
    loadReviews();
}

export function handleSearchInput(event) {
    const keyword = event.target.value;
    // 使用防抖
    if (window.searchTimer) clearTimeout(window.searchTimer);
    window.searchTimer = setTimeout(() => {
        searchReviews(keyword);
    }, 300);
}

export function filterReviews(filters) {
    currentFilters = { ...currentFilters, ...filters };
    loadReviews();
}

export function clearFilters() {
    currentSearch = '';
    currentFilters = {};
    currentSort = { field: 'created_at', order: 'desc' };

    // 重置UI
    const searchInput = document.getElementById('reviews-search');
    if (searchInput) searchInput.value = '';

    const statusSelect = document.getElementById('reviews-status-filter');
    if (statusSelect) statusSelect.value = '';

    const strategySelect = document.getElementById('reviews-strategy-filter');
    if (strategySelect) strategySelect.value = '';

    loadReviews();
}

// 初始化
export function initReviews() {
    // 绑定全局函数
    window.showReviewDetail = showReviewDetail;
    window.deleteReview = deleteReview;
    window.sortReviews = sortReviews;
    window.handleSearchInput = handleSearchInput;
    window.toggleColumnMenu = toggleColumnMenu;
    window.toggleColumn = toggleColumn;
    window.clearFilters = clearFilters;

    // 绑定筛选事件
    const statusSelect = document.getElementById('reviews-status-filter');
    if (statusSelect) {
        statusSelect.addEventListener('change', (e) => filterReviews({ status: e.target.value }));
    }

    const strategySelect = document.getElementById('reviews-strategy-filter');
    if (strategySelect) {
        strategySelect.addEventListener('change', (e) => filterReviews({ strategy: e.target.value }));
    }

    // 点击外部关闭列菜单
    document.addEventListener('click', (e) => {
        const menu = document.getElementById('column-menu');
        const btn = document.querySelector('.column-filter-dropdown button');

        if (menu && menu.classList.contains('show') &&
            !menu.contains(e.target) && !btn.contains(e.target)) {
            menu.classList.remove('show');
        }
    });

    loadReviews();
}
