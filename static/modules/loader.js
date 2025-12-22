/**
 * HTML 模板加载器
 * 负责动态加载页面片段和组件
 */

// 缓存已加载的模板
const templateCache = new Map();

/**
 * 加载 HTML 模板并注入到指定容器
 * @param {string} url - 模板 URL
 * @param {string} targetId - 目标容器 ID
 * @returns {Promise<boolean>} - 是否加载成功
 */
export async function loadTemplate(url, targetId) {
    try {
        const targetElement = document.getElementById(targetId);
        if (!targetElement) {
            console.error(`Target element #${targetId} not found`);
            return false;
        }

        let html = templateCache.get(url);

        if (!html) {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`Failed to load template: ${response.statusText}`);
            }
            html = await response.text();
            templateCache.set(url, html);
        }

        targetElement.innerHTML = html;
        return true;
    } catch (error) {
        console.error(`Error loading template ${url}:`, error);
        return false;
    }
}

/**
 * 加载模态框组件并追加到 body 末尾
 * @param {string} url - 模板 URL
 */
export async function loadComponent(url) {
    try {
        let html = templateCache.get(url);

        if (!html) {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`Failed to load component: ${response.statusText}`);
            }
            html = await response.text();
            templateCache.set(url, html);
        }

        // 创建临时容器解析 HTML
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;

        // 将所有子元素移动到 body
        while (tempDiv.firstChild) {
            document.body.appendChild(tempDiv.firstChild);
        }
        return true;
    } catch (error) {
        console.error(`Error loading component ${url}:`, error);
        return false;
    }
}
