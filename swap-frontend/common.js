/* ================================================
   Comedy Swap — 公共脚本（物品/服务交换平台副站）
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

/* 跳登录页，保留当前页 redirect 回跳参数 */
function redirectToLogin() {
    const here = window.location.pathname + window.location.search;
    window.location.href = '/login.html?redirect=' + encodeURIComponent(here) + '&_=' + Date.now();
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user_id');
    window.location.href = '/login.html?_=' + Date.now();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

/* 截断文本，用于卡片摘要 */
function truncate(text, max) {
    if (!text) return '';
    const s = String(text);
    return s.length > max ? s.slice(0, max) + '…' : s;
}

async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const isFormData = options.body instanceof FormData;
    const headers = isFormData
        ? { 'Authorization': `Bearer ${getToken()}`, ...(options.headers || {}) }
        : { ...authHeaders(), ...(options.headers || {}) };

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        redirectToLogin();
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

/* 发单 / 提交 offer 前调用；未登录跳 login.html 并带 redirect 回跳 */
function requireAuth() {
    const token = getToken();
    const userId = getCurrentUserId();
    if (!token || !userId) {
        redirectToLogin();
        return false;
    }
    return true;
}

/* 登录后回跳：读 redirect 参数（防开放跳转，仅允许本站相对路径） */
function consumeRedirect() {
    const params = new URLSearchParams(window.location.search);
    const redirect = params.get('redirect');
    if (redirect && redirect.startsWith('/') && !redirect.startsWith('//')) {
        return redirect;
    }
    return 'index.html';
}

/* ================================================
   图片上传（POST /swap/upload，FormData 字段 file）
   返回后端给定的图片 URL（如 /static/swap_images/xxx.jpg）
   ================================================ */
async function uploadSwapImage(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiFetch('/swap/upload', { method: 'POST', body: formData });
    const data = await res.json();
    return data.url || data.path || data.image_url || '';
}

/* ================================================
   轻提示 toast
   ================================================ */
function toast(msg, type = 'info') {
    let box = document.getElementById('toast-box');
    if (!box) {
        box = document.createElement('div');
        box.id = 'toast-box';
        document.body.appendChild(box);
    }
    const el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.textContent = msg;
    box.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.remove(), 300);
    }, 2600);
}

/* ================================================
   简易 confirm 弹窗（Promise<boolean>）
   ================================================ */
function confirmDialog(message) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';
        overlay.innerHTML = `
            <div class="confirm-box">
                <p class="confirm-msg">${escapeHtml(message)}</p>
                <div class="confirm-actions">
                    <button class="btn-ghost btn-sm" data-act="cancel">取消</button>
                    <button class="btn-primary btn-sm" data-act="ok">确定</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        const done = (val) => { overlay.remove(); resolve(val); };
        overlay.querySelector('[data-act="ok"]').onclick = () => done(true);
        overlay.querySelector('[data-act="cancel"]').onclick = () => done(false);
        overlay.onclick = (e) => { if (e.target === overlay) done(false); };
    });
}

/* ================================================
   顶栏登录态渲染
   authArea: 元素 id，页面放一个 <div class="auth-area" id="auth-area">
   ================================================ */
function renderAuthArea() {
    const box = document.getElementById('auth-area');
    if (!box) return;
    if (getToken() && getCurrentUserId()) {
        box.innerHTML = `
            <a class="link-me" href="me.html">我的</a>
            <button class="btn-logout" onclick="logout()">退出</button>`;
    } else {
        box.innerHTML = `<a class="btn-login" href="login.html">登录</a>`;
    }
}
