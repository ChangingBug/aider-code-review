/**
 * Aider Code Review Dashboard - 模块化入口
 * 
 * 这是模块化后的前端入口文件，使用 ES6 模块语法。
 * 原有的 app.js 保留作为兼容性备份。
 */

import { initNavigation, navigateTo, getCurrentPage, loadPageData } from './modules/router.js';
import { initSettings, testGitConnection, testVllmConnection, testAider } from './modules/settings.js';
import { initModal } from './modules/modal.js';
import { loadPollingData, initPollingEvents } from './modules/polling.js';
import { initReviewDetail } from './modules/review-detail.js';
import { initReviews } from './modules/reviews.js';
import { loadTemplate, loadComponent } from './modules/loader.js';

// 将全局函数挂载到 window 对象，以便 HTML onclick 调用
window.testGitConnection = testGitConnection;
window.testVllmConnection = testVllmConnection;
window.testAider = testAider;

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('Aider Code Review Dashboard (Modular) v2.0 initialized');

    // 1. 并行加载所有 HTML 模板
    console.log('Loading templates...');
    try {
        await Promise.all([
            loadTemplate('/static/pages/overview.html', 'page-overview'),
            loadTemplate('/static/pages/reviews.html', 'page-reviews'),
            loadTemplate('/static/pages/authors.html', 'page-authors'),
            loadTemplate('/static/pages/projects.html', 'page-projects'),
            loadTemplate('/static/pages/settings.html', 'page-settings'),
            loadComponent('/static/components/modals.html')
        ]);
        console.log('All templates loaded successfully.');
    } catch (e) {
        console.error('Template loading failed:', e);
        alert('页面资源加载失败，请刷新重试');
        return;
    }

    // 2. 模板加载完成后，初始化各个模块
    // 初始化导航
    initNavigation();

    // 初始化设置
    initSettings();

    // 初始化模态框
    initModal();

    // 初始化审查详情（增强版）
    initReviewDetail();

    // 初始化审查列表（增强版）
    initReviews();

    // 初始化轮询事件
    if (typeof initPollingEvents === 'function') {
        initPollingEvents();
    }

    // 加载初始页面
    navigateTo('overview');

    // 定时刷新数据 (每30秒)
    setInterval(() => {
        const currentPage = getCurrentPage();
        console.log('Auto refreshing page: ' + currentPage);
        // 如果当前页面有特定的加载函数，可以优化为只调用该函数，这里简化处理复用路由逻辑
        loadPageData(currentPage);
        
        // 如果有轮询数据加载函数，也执行
        if (typeof loadPollingData === 'function') {
            loadPollingData();
        }
    }, 30000);
});
