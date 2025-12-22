/**
 * 页面路由模块
 */

import { loadOverview } from './overview.js';
import { loadReviews } from './reviews.js';
import { loadAuthors } from './authors.js';
import { loadProjects } from './projects.js';
import { loadSettings } from './settings.js';

const pages = ['overview', 'reviews', 'authors', 'projects', 'settings'];
let currentPage = 'overview';

export function navigateTo(page) {
    if (!pages.includes(page)) return;

    currentPage = page;

    // 更新导航激活状态
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.page === page);
    });

    // 切换页面显示
    pages.forEach(p => {
        const pageEl = document.getElementById(`page-${p}`);
        if (pageEl) {
            pageEl.style.display = p === page ? 'block' : 'none';
        }
    });

    // 加载页面数据
    loadPageData(page);
}

export function loadPageData(page) {
    switch (page) {
        case 'overview':
            loadOverview();
            break;
        case 'reviews':
            loadReviews();
            break;
        case 'authors':
            loadAuthors();
            break;
        case 'projects':
            loadProjects();
            break;
        case 'settings':
            loadSettings();
            break;
    }
}

export function getCurrentPage() {
    return currentPage;
}

// 初始化导航事件
export function initNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navigateTo(link.dataset.page);
        });
    });
}
