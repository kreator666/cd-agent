/* ================================================
   Comedy Agent — 公共脚本
   ================================================ */

const API_BASE = window.location.origin;

function getToken() { return localStorage.getItem('token'); }
function getCurrentUserId() { return localStorage.getItem('user_id'); }

function authHeaders() {
    const token = getToken();
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
    };
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user_id');
    // 加时间戳，避免浏览器缓存旧版 login.html
    window.location.href = '/static/login.html?_=' + Date.now();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const isFormData = options.body instanceof FormData;
    const headers = isFormData
        ? { 'Authorization': `Bearer ${getToken()}`, ...(options.headers || {}) }
        : { ...authHeaders(), ...(options.headers || {}) };

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        logout();
        throw new Error('登录已过期，请重新登录');
    }
    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const errData = await res.clone().json();
            detail = errData.detail || detail;
        } catch {}
        throw new Error(detail);
    }
    return res;
}

async function checkHealth(elementId) {
    const statusEl = document.getElementById(elementId);
    if (!statusEl) return;
    try {
        const res = await fetch(`${API_BASE}/health`, { headers: authHeaders() });
        const data = await res.json();
        if (data.status === 'ok') {
            statusEl.textContent = '就绪';
            statusEl.classList.add('ready');
        } else {
            statusEl.textContent = '异常';
        }
    } catch {
        statusEl.textContent = '离线';
    }
}

function requireAuth() {
    const token = getToken();
    const userId = getCurrentUserId();
    if (!token || !userId) {
        window.location.href = '/static/login.html?_=' + Date.now();
    }
}

/* ================================================
   页面导航（PRD v2 双模式）
   ================================================ */
function goHome() { window.location.href = '/static/index.html?_=' + Date.now(); }
function goSpeed() { window.location.href = '/static/speed.html?_=' + Date.now(); }
function goPro() { window.location.href = '/static/pro.html?_=' + Date.now(); }
function goIPRole(roleId) {
    const ts = '_=' + Date.now();
    if (roleId) {
        window.location.href = `/static/ip-role.html?role_id=${encodeURIComponent(roleId)}&${ts}`;
    } else {
        window.location.href = `/static/ip-role.html?${ts}`;
    }
}
function goSkills() { window.location.href = '/static/skills.html?_=' + Date.now(); }
function goMe() { window.location.href = '/static/me.html?_=' + Date.now(); }
