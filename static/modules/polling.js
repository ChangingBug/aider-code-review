/**
 * 轮询管理模块（完整版）
 * 
 * 从 app.js 迁移的完整仓库管理功能
 */

import { API } from './api.js';
import { formatTime, escapeHtml } from './utils.js';

// 当前编辑的仓库数据
let editingRepoData = null;

// ==================== 数据加载 ====================

export async function loadPollingData() {
    try {
        const [status, repos] = await Promise.all([
            API.get('/polling/status'),
            API.get('/polling/repos')
        ]);

        if (status) {
            updatePollingStatusUI(status);
        }

        if (repos && repos.repos) {
            renderReposList(repos.repos);
        }
    } catch (error) {
        console.error('加载轮询数据失败:', error);
    }
}

function updatePollingStatusUI(status) {
    const statusEl = document.getElementById('polling-status');
    if (!statusEl) return;

    statusEl.className = 'test-result success';
    statusEl.textContent = `✓ 活跃中 (${status.enabled_repos}/${status.repos_count} 个仓库正在监控中)`;
}

// ==================== 仓库列表渲染 ====================

function renderReposList(repos) {
    const container = document.getElementById('repos-list');
    if (!container) return;

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
                <div class="repo-name">${escapeHtml(repo.name)}</div>
                <div class="repo-url">${escapeHtml(repo.url)}</div>
                <div class="repo-meta">
                    分支: ${escapeHtml(repo.branch)} | 
                    模式: ${repo.trigger_mode === 'polling' ? '🔄轮询' : repo.trigger_mode === 'webhook' ? '🔔Webhook' : '🔄🔔混合'} |
                    ${repo.trigger_mode !== 'webhook' ? `间隔: ${repo.polling_interval}分 |` : ''}
                    ${repo.poll_commits ? '✓提交' : ''} 
                    ${repo.poll_mrs ? '✓MR' : ''} |
                    ${repo.enabled ? '🟢启用' : '🔴禁用'}
                    ${repo.clone_status ? ` | 克隆: ${repo.clone_status === 'cloned' ? '✓完成' : repo.clone_status === 'cloning' ? '⏳进行中' : '❌失败'}` : ''}
                    ${repo.last_check_time ? ` | 上次检查: ${formatTime(repo.last_check_time)}` : ''}
                </div>
            </div>
            <div class="repo-actions">
                <button class="btn btn-primary btn-sm" onclick="window.triggerRepoReview('${repo.id}')" title="立即审查">
                    🚀
                </button>
                <button class="btn btn-test btn-sm" onclick="window.showEditRepoModal('${repo.id}')" title="编辑">
                    ✏️
                </button>
                <button class="btn btn-test btn-sm" onclick="window.toggleRepoEnabled('${repo.id}', ${!repo.enabled})">
                    ${repo.enabled ? '禁用' : '启用'}
                </button>
                <button class="btn btn-test btn-sm btn-danger" onclick="window.deleteRepo('${repo.id}')">
                    删除
                </button>
            </div>
        </div>
    `).join('');
}

// ==================== 仓库操作 ====================

// 删除仓库
export async function deleteRepo(repoId) {
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
export async function toggleRepoEnabled(repoId, enabled) {
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

// 手动触发仓库审查
export async function triggerRepoReview(repoId) {
    // 弹出选择审查类型
    const strategy = await showReviewTypeDialog();
    if (!strategy) return; // 用户取消

    try {
        const response = await fetch(`/api/polling/repos/${repoId}/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strategy })
        });

        const result = await response.json();

        if (response.ok) {
            alert('✓ ' + result.message);
        } else {
            alert('触发失败: ' + (result.detail || '未知错误'));
        }
    } catch (error) {
        console.error('触发失败:', error);
        alert('触发失败: ' + error.message);
    } finally {
        loadPollingData();
    }
}

// 显示审查类型选择对话框
function showReviewTypeDialog() {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay active';
        overlay.style.zIndex = '2000';
        overlay.innerHTML = `
            <div class="modal" style="max-width: 400px;">
                <div class="modal-header">
                    <h3 class="modal-title">选择审查类型</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
                </div>
                <div class="modal-body" style="padding: 20px;">
                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <button class="btn btn-primary" style="padding: 15px; font-size: 16px;" id="select-commit">
                            📝 Commit 审查
                            <div style="font-size: 12px; opacity: 0.8; margin-top: 4px;">审查最新提交的代码变更</div>
                        </button>
                        <button class="btn" style="padding: 15px; font-size: 16px; background: var(--success);" id="select-mr">
                            🔀 MR/PR 审查
                            <div style="font-size: 12px; opacity: 0.8; margin-top: 4px;">审查整个分支的代码变更</div>
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        overlay.querySelector('#select-commit').onclick = () => {
            overlay.remove();
            resolve('commit');
        };
        overlay.querySelector('#select-mr').onclick = () => {
            overlay.remove();
            resolve('merge_request');
        };
        overlay.querySelector('.modal-close').onclick = () => {
            overlay.remove();
            resolve(null);
        };
        overlay.onclick = (e) => {
            if (e.target === overlay) {
                overlay.remove();
                resolve(null);
            }
        };
    });
}

// ==================== 添加仓库模态框 ====================

export function showAddRepoModal() {
    document.getElementById('add-repo-modal').classList.add('active');
}

export function closeAddRepoModal() {
    document.getElementById('add-repo-modal').classList.remove('active');
    // 清空表单
    const form = document.getElementById('add-repo-modal');
    if (form) {
        const inputs = form.querySelectorAll('input[type="text"], input[type="password"], input[type="number"]');
        inputs.forEach(input => {
            if (input.id !== 'new-repo-branch') input.value = '';
        });
        const resultEl = document.getElementById('add-repo-result');
        if (resultEl) resultEl.textContent = '';
    }
}

// 切换鉴权方式显示
export function toggleAuthFields() {
    const authType = document.getElementById('new-repo-auth-type')?.value;
    const httpFields = document.getElementById('http-auth-fields');
    const tokenFields = document.getElementById('token-auth-fields');

    if (httpFields) httpFields.style.display = authType === 'http_basic' ? 'grid' : 'none';
    if (tokenFields) tokenFields.style.display = authType === 'token' ? 'block' : 'none';
}

// 平台切换
export function onPlatformChange() {
    const url = document.getElementById('new-repo-url')?.value.trim();
    if (url) {
        const platform = document.getElementById('new-repo-platform')?.value;
        const apiUrl = inferApiUrl(url, platform);
        if (apiUrl) {
            const apiUrlInput = document.getElementById('new-repo-api-url');
            if (apiUrlInput) apiUrlInput.value = apiUrl;
        }
    }
    updateWebhookUrl();
}

// 切换触发模式字段显示
export function toggleTriggerModeFields() {
    const triggerMode = document.getElementById('new-repo-trigger-mode')?.value || 'polling';

    const webhookSecretGroup = document.getElementById('webhook-secret-group');
    const pollingConfigGroup = document.getElementById('polling-config-group');
    const webhookConfigGroup = document.getElementById('webhook-config-group');

    if (webhookSecretGroup) {
        webhookSecretGroup.style.display = (triggerMode === 'webhook' || triggerMode === 'both') ? 'block' : 'none';
    }

    if (pollingConfigGroup) {
        pollingConfigGroup.style.display = (triggerMode === 'polling' || triggerMode === 'both') ? 'block' : 'none';
    }

    if (webhookConfigGroup) {
        webhookConfigGroup.style.display = (triggerMode === 'webhook' || triggerMode === 'both') ? 'block' : 'none';
        if (triggerMode === 'webhook' || triggerMode === 'both') {
            updateWebhookUrl();
        }
    }
}

// 更新Webhook URL显示
export function updateWebhookUrl() {
    const platform = document.getElementById('new-repo-platform')?.value || 'gitlab';
    const webhookUrlDisplay = document.getElementById('webhook-url-display');

    if (webhookUrlDisplay) {
        const baseUrl = window.location.origin;
        const webhookUrl = `${baseUrl}/api/webhook/${platform}`;
        webhookUrlDisplay.value = webhookUrl;
    }
}

// 复制Webhook URL
export function copyWebhookUrl() {
    const webhookUrlDisplay = document.getElementById('webhook-url-display');
    if (webhookUrlDisplay) {
        webhookUrlDisplay.select();
        document.execCommand('copy');
        alert('✓ Webhook URL已复制');
    }
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

// URL变化时自动解析
let urlParseTimer = null;
export function onRepoUrlChange() {
    const url = document.getElementById('new-repo-url')?.value.trim();
    if (!url) return;

    const platform = document.getElementById('new-repo-platform')?.value;
    const apiUrl = inferApiUrl(url, platform);
    if (apiUrl) {
        const apiUrlInput = document.getElementById('new-repo-api-url');
        if (apiUrlInput) apiUrlInput.value = apiUrl;
    }

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
                const nameInput = document.getElementById('new-repo-name');
                if (nameInput) nameInput.value = data.name;
            }
        } catch (e) {
            console.error('解析URL失败:', e);
        }
    }, 500);
}

// 加载分支列表
export async function loadBranches() {
    const resultEl = document.getElementById('add-repo-result');
    const btn = document.getElementById('load-branches-btn');
    const select = document.getElementById('new-repo-branch-select');

    const url = document.getElementById('new-repo-url')?.value.trim();
    const platform = document.getElementById('new-repo-platform')?.value;
    const authType = document.getElementById('new-repo-auth-type')?.value;
    const token = document.getElementById('new-repo-token')?.value;
    const httpUser = document.getElementById('new-repo-http-user')?.value;
    const httpPassword = document.getElementById('new-repo-http-password')?.value;

    if (!url) {
        if (resultEl) {
            resultEl.className = 'test-result error';
            resultEl.textContent = '请先输入仓库URL';
        }
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.textContent = '加载中...';
    }
    if (resultEl) {
        resultEl.className = 'test-result loading';
        resultEl.textContent = '⏳ 正在获取分支列表...';
    }

    try {
        const response = await fetch('/api/polling/branches', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url, platform, auth_type: authType,
                token, http_user: httpUser, http_password: httpPassword
            })
        });
        const data = await response.json();

        if (select) {
            select.innerHTML = '<option value="">-- 选择分支 --</option>';
            if (data.branches && data.branches.length > 0) {
                data.branches.forEach(branch => {
                    const option = document.createElement('option');
                    option.value = branch;
                    option.textContent = branch;
                    select.appendChild(option);
                });
                if (resultEl) {
                    resultEl.className = 'test-result success';
                    resultEl.textContent = `✓ 加载了 ${data.branches.length} 个分支`;
                }
            } else {
                if (resultEl) {
                    resultEl.className = 'test-result error';
                    resultEl.textContent = '未找到分支，请检查URL和认证信息';
                }
            }
        }
    } catch (e) {
        if (resultEl) {
            resultEl.className = 'test-result error';
            resultEl.textContent = `加载失败: ${e.message}`;
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '🔄 加载';
        }
    }
}

// 更新分支输入框
export function updateBranchInput() {
    const select = document.getElementById('new-repo-branch-select');
    const input = document.getElementById('new-repo-branch');
    if (select?.value && input) {
        input.value = select.value;
    }
}

// 评论开关与API地址字段联动
export function toggleApiUrlField() {
    const enableComment = document.getElementById('new-repo-enable-comment')?.checked;
    const apiUrlField = document.getElementById('api-url-field');
    if (apiUrlField) apiUrlField.style.display = enableComment ? 'block' : 'none';
}

// 添加仓库
export async function addRepo() {
    const resultEl = document.getElementById('add-repo-result');

    const name = document.getElementById('new-repo-name')?.value.trim();
    const url = document.getElementById('new-repo-url')?.value.trim();
    const branch = document.getElementById('new-repo-branch')?.value.trim() || 'main';
    const platform = document.getElementById('new-repo-platform')?.value;
    const authType = document.getElementById('new-repo-auth-type')?.value;
    const token = document.getElementById('new-repo-token')?.value;
    const httpUser = document.getElementById('new-repo-http-user')?.value;
    const httpPassword = document.getElementById('new-repo-http-password')?.value;
    const apiUrl = document.getElementById('new-repo-api-url')?.value.trim();
    const localPath = document.getElementById('new-repo-local-path')?.value.trim();
    const effectiveTime = document.getElementById('new-repo-effective-time')?.value;
    const pollCommits = document.getElementById('new-repo-commits')?.checked;
    const pollMrs = document.getElementById('new-repo-mrs')?.checked;
    const enableComment = document.getElementById('new-repo-enable-comment')?.checked;
    const triggerMode = document.getElementById('new-repo-trigger-mode')?.value || 'polling';
    const webhookSecret = document.getElementById('new-repo-webhook-secret')?.value || '';
    const pollingInterval = parseInt(document.getElementById('new-repo-polling-interval')?.value) || 5;

    if (!url) {
        if (resultEl) {
            resultEl.className = 'test-result error';
            resultEl.textContent = '请输入仓库URL';
        }
        return;
    }

    if (resultEl) {
        resultEl.className = 'test-result loading';
        resultEl.textContent = '⏳ 正在添加仓库...';
    }

    try {
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
                polling_interval: pollingInterval,
                enable_comment: enableComment,
                trigger_mode: triggerMode,
                webhook_secret: webhookSecret
            })
        });

        if (!response.ok) {
            const error = await response.json();
            if (resultEl) {
                resultEl.className = 'test-result error';
                resultEl.textContent = '添加失败: ' + (error.detail || '未知错误');
            }
            return;
        }

        const repoData = await response.json();
        const repoId = repoData.repo?.id;

        if (resultEl) resultEl.textContent = '⏳ 仓库已添加，正在克隆代码...';

        if (repoId) {
            const cloneResponse = await fetch(`/api/polling/repos/${repoId}/clone`, {
                method: 'POST'
            });
            const cloneResult = await cloneResponse.json();

            if (cloneResult.success) {
                if (resultEl) {
                    resultEl.className = 'test-result success';
                    resultEl.textContent = `✓ ${cloneResult.message}`;
                }

                setTimeout(() => {
                    closeAddRepoModal();
                    loadPollingData();
                }, 1500);
            } else {
                if (resultEl) {
                    resultEl.className = 'test-result error';
                    resultEl.textContent = `仓库已添加，但克隆失败: ${cloneResult.message}`;
                }
                loadPollingData();
            }
        }
    } catch (error) {
        if (resultEl) {
            resultEl.className = 'test-result error';
            resultEl.textContent = '添加失败: ' + error.message;
        }
    }
}

// ==================== 编辑仓库模态框 ====================

export async function showEditRepoModal(repoId) {
    try {
        const response = await fetch('/api/polling/repos');
        const data = await response.json();
        const repo = data.repos.find(r => r.id === repoId);

        if (!repo) {
            alert('未找到仓库');
            return;
        }

        editingRepoData = repo;

        // 填充编辑表单
        const setValue = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.value = value || '';
        };
        const setChecked = (id, checked) => {
            const el = document.getElementById(id);
            if (el) el.checked = checked;
        };

        setValue('edit-repo-id', repo.id);
        setValue('edit-repo-name', repo.name);
        setValue('edit-repo-url', repo.url);
        setValue('edit-repo-branch', repo.branch || 'main');
        setValue('edit-repo-platform', repo.platform || 'gitlab');
        setValue('edit-repo-auth-type', repo.auth_type || 'http_basic');
        setValue('edit-repo-http-user', repo.http_user);
        setValue('edit-repo-http-password', repo.http_password);
        setValue('edit-repo-token', repo.token);
        setValue('edit-repo-api-url', repo.api_url);
        setValue('edit-repo-polling-interval', repo.polling_interval || 5);
        setChecked('edit-repo-commits', repo.poll_commits);
        setChecked('edit-repo-mrs', repo.poll_mrs);
        setChecked('edit-repo-enable-comment', repo.enable_comment);

        toggleEditAuthFields();

        document.getElementById('edit-repo-modal')?.classList.add('active');
    } catch (error) {
        console.error('获取仓库信息失败:', error);
        alert('获取仓库信息失败');
    }
}

export function closeEditRepoModal() {
    document.getElementById('edit-repo-modal')?.classList.remove('active');
    editingRepoData = null;
}

export function toggleEditAuthFields() {
    const authType = document.getElementById('edit-repo-auth-type')?.value;
    const httpFields = document.getElementById('edit-http-auth-fields');
    const tokenFields = document.getElementById('edit-token-auth-fields');

    if (httpFields) httpFields.style.display = authType === 'http_basic' ? 'grid' : 'none';
    if (tokenFields) tokenFields.style.display = authType === 'token' ? 'block' : 'none';
}

export async function saveEditedRepo() {
    const repoId = document.getElementById('edit-repo-id')?.value;
    const resultEl = document.getElementById('edit-repo-result');

    const getValue = (id) => document.getElementById(id)?.value || '';
    const getChecked = (id) => document.getElementById(id)?.checked || false;

    const updates = {
        name: getValue('edit-repo-name').trim(),
        url: getValue('edit-repo-url').trim(),
        branch: getValue('edit-repo-branch').trim(),
        platform: getValue('edit-repo-platform'),
        auth_type: getValue('edit-repo-auth-type'),
        http_user: getValue('edit-repo-http-user'),
        http_password: getValue('edit-repo-http-password'),
        token: getValue('edit-repo-token'),
        api_url: getValue('edit-repo-api-url').trim(),
        poll_commits: getChecked('edit-repo-commits'),
        poll_mrs: getChecked('edit-repo-mrs'),
        polling_interval: parseInt(getValue('edit-repo-polling-interval')) || 5,
        enable_comment: getChecked('edit-repo-enable-comment'),
    };

    if (resultEl) {
        resultEl.className = 'test-result loading';
        resultEl.textContent = '⏳ 正在保存...';
    }

    try {
        const response = await fetch(`/api/polling/repos/${repoId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        if (response.ok) {
            if (resultEl) {
                resultEl.className = 'test-result success';
                resultEl.textContent = '✓ 保存成功';
            }
            setTimeout(() => {
                closeEditRepoModal();
                loadPollingData();
            }, 1000);
        } else {
            const error = await response.json();
            if (resultEl) {
                resultEl.className = 'test-result error';
                resultEl.textContent = '保存失败: ' + (error.detail || '未知错误');
            }
        }
    } catch (error) {
        if (resultEl) {
            resultEl.className = 'test-result error';
            resultEl.textContent = '保存失败: ' + error.message;
        }
    }
}

// ==================== 初始化 ====================

export function initPollingEvents() {
    // 绑定全局函数
    window.deleteRepo = deleteRepo;
    window.triggerRepoReview = triggerRepoReview;
    window.toggleRepoEnabled = toggleRepoEnabled;
    window.showEditRepoModal = showEditRepoModal;
    window.closeEditRepoModal = closeEditRepoModal;
    window.saveEditedRepo = saveEditedRepo;
    window.toggleEditAuthFields = toggleEditAuthFields;

    window.showAddRepoModal = showAddRepoModal;
    window.closeAddRepoModal = closeAddRepoModal;
    window.addRepo = addRepo;
    window.toggleAuthFields = toggleAuthFields;
    window.onPlatformChange = onPlatformChange;
    window.toggleTriggerModeFields = toggleTriggerModeFields;
    window.updateWebhookUrl = updateWebhookUrl;
    window.copyWebhookUrl = copyWebhookUrl;
    window.onRepoUrlChange = onRepoUrlChange;
    window.loadBranches = loadBranches;
    window.updateBranchInput = updateBranchInput;
    window.toggleApiUrlField = toggleApiUrlField;

    // 初始加载
    loadPollingData();
}
