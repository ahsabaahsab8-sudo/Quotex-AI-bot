/* Small API client — cookie-authenticated fetch wrapper. */
async function api(path, opts = {}) {
  const res = await fetch('/api' + path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    method: opts.method || 'GET',
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty */ }
  if (!res.ok) {
    const err = new Error((data && data.detail) ? (typeof data.detail === 'string' ? data.detail : 'Error') : 'Request failed');
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(msg, type = 'info') {
  const wrap = document.getElementById('toast-wrap');
  const el = document.createElement('div');
  el.className = 'toast ' + (type === 'error' ? 'err' : type === 'ok' ? 'ok' : '');
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(30px)'; el.style.transition = 'all .3s'; }, 3200);
  setTimeout(() => el.remove(), 3600);
}

function fmtDT(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function esc(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function spinner() { return '<span class="spinner"></span>'; }

/* Global state */
const State = {
  user: null,
  pairs: null,
  timeframes: null,
  theme: localStorage.getItem('theme') || 'dark',
};