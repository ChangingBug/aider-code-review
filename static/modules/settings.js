/**
 * 设置页面模块
 */

import { API } from './api.js';

export async function loadSettings() {
    const data = await API.get('/settings');
    if (!data) return;

    // 填充表单
    Object.entries(data).forEach(([key, info]) => {
        const input = document.getElementById(key);
        if (input) {
            if (input.type === 'checkbox') {
                input.checked = info.value === 'true';
            } else {
                input.value = info.value || '';
            }
        }
    });
}

export async function saveSettings(event) {
    event.preventDefault();

    const form = document.getElementById('settings-form');
    const formData = new FormData(form);

    const settings = {};
    formData.forEach((value, key) => {
        settings[key] = value;
    });

    // 处理复选框
    form.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        settings[cb.name] = cb.checked ? 'true' : 'false';
    });

    const result = await API.post('/settings', settings);

    const statusEl = document.getElementById('settings-status');
    if (statusEl) {
        if (result && result.status === 'success') {
            statusEl.textContent = '设置已保存';
            statusEl.className = 'status-message success';
        } else {
            statusEl.textContent = '保存失败';
            statusEl.className = 'status-message error';
        }

        setTimeout(() => {
            statusEl.textContent = '';
            statusEl.className = 'status-message';
        }, 3000);
    }
}

export async function testGitConnection() {
    const btn = document.getElementById('test-git-btn');
    const result = document.getElementById('git-test-result');

    if (btn) btn.disabled = true;
    if (result) result.textContent = '测试中...';

    const response = await API.post('/test/git');

    if (btn) btn.disabled = false;
    if (result) {
        if (response && response.success) {
            result.textContent = '✓ 连接成功';
            result.className = 'test-result success';
        } else {
            result.textContent = `✗ ${response?.message || '连接失败'}`;
            result.className = 'test-result error';
        }
    }
}

export async function testVllmConnection() {
    const btn = document.getElementById('test-vllm-btn');
    const result = document.getElementById('vllm-test-result');

    if (btn) btn.disabled = true;
    if (result) result.textContent = '测试中...';

    const response = await API.post('/test/vllm');

    if (btn) btn.disabled = false;
    if (result) {
        if (response && response.success) {
            result.textContent = `✓ ${response.message}`;
            result.className = 'test-result success';
        } else {
            result.textContent = `✗ ${response?.message || '连接失败'}`;
            result.className = 'test-result error';
        }
    }
}

export async function testAider() {
    const btn = document.getElementById('test-aider-btn');
    const result = document.getElementById('aider-test-result');

    if (btn) btn.disabled = true;
    if (result) result.textContent = '测试中...';

    const response = await API.post('/test/aider');

    if (btn) btn.disabled = false;
    if (result) {
        if (response && response.success) {
            result.textContent = `✓ Aider v${response.details?.version || '?'}`;
            result.className = 'test-result success';
        } else {
            result.textContent = `✗ ${response?.message || 'Aider不可用'}`;
            result.className = 'test-result error';
        }
    }
}

// 初始化设置页面事件
export function initSettings() {
    const form = document.getElementById('settings-form');
    if (form) {
        form.addEventListener('submit', saveSettings);
    }
}
