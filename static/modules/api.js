/**
 * API 调用模块
 */

export const API = {
    async get(endpoint) {
        try {
            const response = await fetch(`/api${endpoint}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`API GET ${endpoint} 失败:`, error);
            return null;
        }
    },

    async post(endpoint, data = {}) {
        try {
            const response = await fetch(`/api${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`API POST ${endpoint} 失败:`, error);
            return null;
        }
    },

    async put(endpoint, data = {}) {
        try {
            const response = await fetch(`/api${endpoint}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`API PUT ${endpoint} 失败:`, error);
            return null;
        }
    },

    async delete(endpoint) {
        try {
            const response = await fetch(`/api${endpoint}`, { method: 'DELETE' });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`API DELETE ${endpoint} 失败:`, error);
            return null;
        }
    }
};
