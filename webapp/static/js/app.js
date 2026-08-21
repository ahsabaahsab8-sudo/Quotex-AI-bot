/* ── Quotex AI Pro — SPA router + page views ─────────────────────── */

let GoogleCredentialPending = null;
const ROUTES = {
  '/': { title: 'Home', render: renderHome, load: loadHomeData },
  '/live-chart': { title: 'Live Chart', render: renderLiveChart },
  '/signals/llm': { title: 'LLM Signals', render: renderSignalWizard('llm') },
  '/signals/vision': { title: 'Vision Signals', render: renderSignalWizard('vision') },
  '/history': { title: 'My Signals', render: renderHistory },
  '/credits': { title: 'Credits & Billing', render: renderCredits },
  '/pricing': { title: 'Pricing', render: renderPricing },
};

document.addEventListener('DOMContentLoaded', () => {
  setTheme(State.theme);
  bindTopbarActions();
  router();
  window.addEventListener('hashchange', router);
});

function bindTopbarActions() {
  document.getElementById('theme-toggle').onclick = () => setTheme(State.theme === 'dark' ? 'light' : 'dark');
  document.getElementById('logout-btn').onclick = async () => {
    await api('/auth/logout', { method: 'POST' });
    location.reload();
  };
  document.querySelector('.mobile-menu').onclick = () => {
    document.querySelector('.sidebar').classList.toggle('open');
  };
  document.getElementById('demo-login').onclick = async () => {
    try {
      await api('/auth/demo', { method: 'POST', body: {} });
      location.reload();
    } catch (e) { toast(e.message, 'error'); }
  };
}

function setTheme(t) {
  State.theme = t;
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
  document.getElementById('theme-toggle').textContent = t === 'dark' ? '🌙' : '☀️';
}

/* ── ROUTER ── */
function currentRoute() {
  const h = location.hash.replace(/^#/, '') || '/';
  return ROUTES[h] ? h : '/';
}

async function router() {
  const route = currentRoute();
  const needAuth = true;
  if (needAuth) {
    try {
      State.user = await api('/me');
    } catch (e) {
      showAuth();
      return;
    }
  }
  showApp();
  document.querySelectorAll('.nav-item').forEach(a =>
    a.classList.toggle('active', (a.dataset.route || '') === route));
  const title = ROUTES[route].title;
  document.querySelector('#page-title').textContent = title;
  const view = document.getElementById('view');
  view.innerHTML = '<div class="empty">' + spinner() + '</div>';
  try {
    if (ROUTES[route].load) await ROUTES[route].load();
    view.innerHTML = '';
    ROUTES[route].render(view);
  } catch (e) {
    view.innerHTML = '<div class="empty">Error loading page: ' + esc(e.message) + '</div>';
  }
  if (route === '/live-chart') return; // live page manages its own cleanup
}

function showAuth() {
  document.getElementById('auth-screen').classList.remove('hidden');
  document.getElementById('app-shell').classList.add('hidden');
  const demoWrap = document.getElementById('demo-login-wrap');
  api('/health').then(() => {});
  fetch('/api/demo_mode').then(r => r.json()).then(d => {
    if (d.demo) demoWrap.classList.remove('hidden');
  }).catch(() => {});
}

function showApp() {
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('app-shell').classList.remove('hidden');
  if (State.user) {
    const u = State.user;
    document.getElementById('user-avatar').src = u.avatar || 'data:image/svg+xml,' + encodeURIComponent("<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'><rect width='28' height='28' rx='14' fill='#334155'/><text x='14' y='19' font-size='14' fill='#fff' text-anchor='middle'>" + (u.name ? u.name[0].toUpperCase() : '?') + "</text></svg>");
    document.getElementById('user-name').textContent = u.name.split(' ')[0] || 'User';
    document.getElementById('mini-balance').textContent = Math.round(u.credits) + ' ⚡';
  }
}

/* Google login setup (called once) */
let G_CLIENT_ID = null;
window.onload = async () => {
  try {
    const cfg = await fetch('/api/config').then(r => r.json());
    G_CLIENT_ID = cfg.google_client_id;
  } catch (e) {}
  if (G_CLIENT_ID && window.google && google.accounts && google.accounts.id) {
    google.accounts.id.initialize({ client_id: G_CLIENT_ID, callback: handleGoogleCredential });
    google.accounts.id.renderButton(document.getElementById('google-login'), {
      type: 'standard', theme: 'outline', size: 'large', shape: 'rectangular',
    });
  }
};

const handleGoogleCredential = async (cred) => {
  try {
    await api('/auth/google', { method: 'POST', body: { id_token: cred.credential } });
    location.reload();
  } catch (e) { toast('Google login failed: ' + e.message, 'error'); }
};

/* ── PAGE: HOME ── */
let homeChart = null;
async function loadHomeData() {
  const [me, signals] = await Promise.all([api('/me'), api('/signals?limit=5')]);
  State.user = me;
  window.__signals = signals;
}
function renderHome(view) {
  const user = State.user;
  const signals = window.__signals || [];
  const done = signals.filter(s => s.status === 'done');
  const wins = done.filter(s => s.direction === 'BUY').length;
  const winrate = done.length ? Math.round(wins / done.length * 100) : 0;
  const recent = signals.slice(0, 5);

  const renderRows = recent.map(s => `
    <tr>
      <td><b>${esc(s.pair)}</b>${s.original_pair && s.original_pair !== s.pair ? ' → ' : ''}</td>
      <td>${esc(s.tf_label)} · ${s.model_type.toUpperCase()}</td>
      <td><span class="stat-badge ${s.direction === 'BUY' ? 'badge-buy' : s.direction === 'SELL' ? 'badge-sell' : 'badge-skip'}">${esc(s.direction) || 'SKIP'}</span></td>
      <td>${s.confidence}%</td>
      <td>${fmtDT(s.created_at)}</td>
    </tr>`).join('') || '<tr><td colspan="5" class="empty">No signals yet — run your first one!</td></tr>';

  view.innerHTML = `
    <div class="grid grid-4">
      <div class="card"><div class="kpi-label">Credits</div>
        <div class="kpi-value">${Math.round(user.credits)}</div>
        <div class="kpi-sub">${user.plan} plan ${user.plan_credits_per_month ? '· ' + user.plan_credits_per_month + ' /mo' : ''}</div></div>
      <div class="card"><div class="kpi-label">Signals</div>
        <div class="kpi-value">${signals.length}</div>
        <div class="kpi-sub">last 10 cost ~${Math.round(signals.length)}0 ⚡</div></div>
      <div class="card"><div class="kpi-label">Win rate</div>
        <div class="kpi-value">${winrate}%</div>
        <div class="kpi-sub">${wins}/${done.length} BUY signals</div></div>
      <div class="card"><div class="kpi-label">Status</div>
        <div class="kpi-value" style="color:var(--accent-2)">●</div>
        <div class="kpi-sub">Quotex connected</div></div>
    </div>

    <div class="grid grid-2">
      <div class="card hover">
        <h3>🚀 New Signal</h3>
        <p style="color:var(--text-2);font-size:13px;margin-bottom:16px">Pick a pair &amp; timeframe, our 3-stage AI vote gives you BUY/SELL with majority confidence in ~30–45s.</p>
        <div class="signals-cta">
          <a class="btn btn-primary quick-btn" href="#/signals/vision">👁️ Vision AI</a>
          <a class="btn btn-ghost quick-btn" href="#/signals/llm">🤖 LLM AI</a>
        </div>
      </div>
      <div class="card hover">
        <h3>📊 Usage</h3>
        <canvas id="usage-chart" height="120"></canvas>
      </div>
    </div>

    <div class="card">
      <h3>🕒 Recent Signals</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Pair</th><th>TF / Model</th><th>Direction</th><th>Confidence</th><th>Time</th></tr></thead>
        <tbody>${renderRows}</tbody>
      </table></div>
    </div>`;

  drawHomeChart(recent);
}

function drawHomeChart(recent) {
  const el = document.getElementById('usage-chart');
  if (!el || !window.Chart) return;
  const buys = recent.filter(s => s.direction === 'BUY').length;
  const sells = recent.filter(s => s.direction === 'SELL').length;
  homeChart = new Chart(el, {
    type: 'doughnut',
    data: { labels: ['BUY', 'SELL', 'SKIP'],
      datasets: [{ data: [buys, sells, Math.max(recent.length - buys - sells, 0)],
        backgroundColor: ['#10B981', '#F43F5E', '#64748B'] }] },
    options: { plugins: { legend: { position: 'bottom', labels: { color: State.theme === 'dark' ? '#9CA3AF' : '#475569' } } }, responsive: true },
  });
}

/* ── PAGE: SIGNAL WIZARD ── */
function renderSignalWizard(model_type) {
  return async function (view) {
    let pairs = null;
    try { pairs = await api('/pairs'); } catch (e) { pairs = null; }
    const tfs = (await api('/timeframes')).timeframes;

    view.innerHTML = `
      <div class="grid grid-2">
        <div class="card">
          <h3>${model_type === 'vision' ? '👁️ Vision AI Signal' : '🤖 LLM Signal'}</h3>
          <div class="field">
            <label>Asset category</label>
            <select id="pair-cat" class="select">
              <option value="all">All</option>
              <option value="OTC">OTC</option>
              <option value="REAL">Standard</option>
              <option value="CRYPTO">Crypto</option>
            </select>
          </div>
          <div class="field">
            <label>Pair</label>
            <select id="pair-select" class="select">${pairs ? '' : '<option>loading pairs…</option>'}</select>
          </div>
          <div class="field">
            <label>Timeframe</label>
            <select id="tf-select" class="select">
              ${tfs.map(t => `<option value="${t}">${tfLabel(t)}</option>`).join('')}
            </select>
          </div>
          <button id="run-signal" class="btn btn-primary btn-block">▶ Get Signal (10 ⚡)</button>
          <p style="font-size:12px;color:var(--text-3);margin-top:10px">Costs 10 credits. Refunded automatically if no signal is produced.</p>
        </div>
        <div class="card">
          <h3>Live Progress</h3>
          <div id="pipeline" class="pipeline">
            <div class="empty">Choose a pair and press <b>Get Signal</b>.</div>
          </div>
        </div>
      </div>
      <div id="result-slot"></div>`;

    // category -> pairs
    const allPairs = pairs ? [...(pairs.OTC || []), ...(pairs.REAL || []), ...(pairs.CRYPTO || [])] : [];
    const catPairs = {
      all: allPairs,
      OTC: pairs ? pairs.OTC : [],
      REAL: pairs ? pairs.REAL : [],
      CRYPTO: pairs ? pairs.CRYPTO : [],
    };
    const fillPairs = (cat) => {
      const sel = document.getElementById('pair-select');
      const list = catPairs[cat] || [];
      if (!allPairs.length && !list.length) { sel.innerHTML = '<option value="">No pairs available — check Quotex connection</option>'; return; }
      const src = list.length ? list : allPairs;
      sel.innerHTML = src.slice(0, 400).map(p =>
        `<option value="${esc(p.symbol)}">${esc(p.label)}${p.payout ? ` — ${p.payout}%` : ''}</option>`).join('');
    };
    document.getElementById('pair-cat').onchange = (e) => fillPairs(e.target.value);
    fillPairs('all');

    document.getElementById('run-signal').onclick = async (ev) => {
      const pair = document.getElementById('pair-select').value;
      const tf = parseInt(document.getElementById('tf-select').value, 10);
      if (!pair) return toast('Pick a pair first', 'error');
      const btn = ev.target;
      btn.disabled = true;
      btn.innerHTML = spinner() + ' Running…';
      try {
        const { job_id } = await api('/signal', { method: 'POST', body: { pair, timeframe_seconds: tf, model_type } });
        await pollJob(view, job_id, model_type);
      } catch (e) {
        toast(e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '▶ Get Signal (10 ⚡)';
      }
    };
    view.style.display = 'block';
    document.getElementById('pipeline').innerHTML = '';
  };
}

async function pollJob(view, job_id, model_type) {
  const pipe = document.getElementById('pipeline') || view.querySelector('#pipeline');
  const slot = document.getElementById('result-slot') || view.querySelector('#result-slot');
  if (slot) slot.innerHTML = '';
  if (pipe) pipe.innerHTML = '';

  const STEPS = [
    'Connecting to Quotex', 'Getting market data + indicators',
    'Analyzing market', 'Checking news', 'Running 3-stage AI vote',
  ];
  for (let i = 0; i < 5; i++) {
    const el = document.createElement('div');
    el.className = 'step active';
    el.innerHTML = `<div class="step-num">${i + 1}</div>
      <div class="step-info"><div class="step-title">${STEPS[i]}</div><div class="step-detail">…</div></div>
      <div class="step-state">${spinner()}</div>`;
    if (pipe) pipe.appendChild(el);
  }

  const stepEls = [...(pipe ? pipe.children : [])];
  let lastStep = 0, lastDetail = '';

  const refresh = async () => {
    const j = await api('/signal/' + job_id);
    const step = Math.max(1, j.step || 1);
    stepEls.forEach((el, i) => {
      const done = i < step - 1;
      const active = i === step - 1 && j.status === 'running';
      el.className = 'step ' + (done ? 'done' : active ? 'active' : '');
      el.querySelector('.step-num').textContent = done ? '✓' : (i + 1);
      el.querySelector('.step-state').innerHTML = done ? '✅' : active ? spinner() : '⏳';
    });
    if (j.progress_text && j.progress_text !== lastDetail) {
      const activeEl = stepEls[step - 1];
      if (activeEl) activeEl.querySelector('.step-detail').textContent = j.progress_text;
    }
    if (['done', 'skipped', 'failed'].includes(j.status)) {
      if (j.status === 'failed') { toast('Signal failed: ' + (j.error || 'unknown'), 'error'); return true; }
      renderSignalResult(slot, j.result, model_type, stepEls, j.status);
      return true;
    }
    return false;
  };
  await refresh();
  const timer = setInterval(async () => {
    try {
      if (await refresh()) clearInterval(timer);
    } catch (e) { clearInterval(timer); toast(e.message, 'error'); }
  }, 2500);
}

function renderSignalResult(slot, result, model_type, stepEls, status) {
  if (!slot) return;
  if (stepEls) {
    stepEls.forEach(el => { el.className = 'step done'; el.querySelector('.step-num').textContent = '✓'; el.querySelector('.step-state').textContent = '✅'; });
  }
  if (!result || result.direction === 'SKIP' || result.skipped) {
    slot.innerHTML = `<div class="result-card"><div class="result-direction" style="color:var(--text-2)">⏭️ No signal</div>
      <p style="color:var(--text-2);margin-top:8px">${esc(result?.reason || 'AI models determined no reliable trade.')}</p>
      <p style="font-size:12px;color:var(--text-3);margin-top:8px">(credits refunded automatically)</p></div>`;
    return;
  }

  const dir = result.direction || 'BUY';
  const conf = result.confidence || 0;
  const votes = result.votes || [];
  const buyCount = votes.filter(v => v.sign === 'BUY').length;
  const sellCount = votes.filter(v => v.sign === 'SELL').length;

  const voteRows = votes.map(v => `
    <div class="vote-row">
      <div class="vote-model">${esc(v.model)}</div>
      <div style="flex:1"></div>
      <div><span class="vote-sign ${v.sign === 'BUY' ? 'buy' : v.sign === 'SELL' ? 'sell' : ''}">${v.sign === 'SKIP' ? 'SKIP' : v.sign}</span></div>
      <div class="vote-conf">${v.confidence}%</div>
      <div class="vote-check">${v.sign === dir ? '✅' : v.sign === 'SKIP' ? '—' : '❌'}</div>
    </div>`).join('') || '<div class="empty">No model votes recorded</div>';

  const reasoning = concatReasoning(result);

  const countdown = Math.floor((result.timeframe_seconds || 60));
  slot.innerHTML = `
    <div class="result-card ${dir === 'BUY' ? 'buy' : 'sell'}">
      <div class="result-top">
        <div>
          <div class="result-pair">${esc(result.pair || '')} · ${esc(result.tf_label || '')}${result.note ? ' <span style="color:var(--gold)">· ' + esc(result.note) + '</span>' : ''}</div>
          <div class="result-time">${model_type.toUpperCase()} system · ${fmtDT(new Date().toISOString())}</div>
        </div>
        <div style="text-align:right">
          <div class="countdown" id="tf-countdown">⏱ Next candle closes in ${countdown}s</div>
        </div>
      </div>
      <div class="result-direction ${dir === 'BUY' ? 'buy' : 'sell'}">${dir === 'BUY' ? '▲ BUY' : '▼ SELL'} <span class="result-confidence">${conf}%</span></div>
      <div style="color:var(--text-2);font-size:13px;margin-top:6px">${result.martingale_recommendation ? 'Martingale: <b>' + esc(result.martingale_recommendation) + '</b>' : ''} · Majority: <b>${buyCount} BUY / ${sellCount} SELL</b> · Math score ${result.math_score ?? '—'}/10</div>

      <div class="vote-list">${voteRows}</div>

      <div class="reasoning-panel">
        <button class="reasoning-toggle" data-open="0">▶ View Reasoning &amp; Analysis</button>
        <div class="reasoning-box hidden">${esc(reasoning)}</div>
      </div>
      ${result.has_chart ? `<div class="chart-img" data-chart-slot=""></div>` : ''}
    </div>`;

  const toggle = slot.querySelector('.reasoning-toggle');
  toggle.onclick = () => {
    const box = slot.querySelector('.reasoning-box');
    const open = box.classList.toggle('hidden');
    toggle.textContent = open ? '▶ View Reasoning & Analysis' : '▼ Hide Reasoning';
  };

  // countdown ticking
  let remain = countdown;
  setInterval(() => {
    remain -= 1;
    if (remain < 0) remain = countdown;
    const c = slot.querySelector('#tf-countdown');
    if (c) c.textContent = `⏱ Next candle closes in ${remain}s`;
  }, 1000);
}

function concatReasoning(result) {
  const parts = [];
  if (result.reason) parts.push('RESULT\n' + result.reason);
  const votes = result.votes || [];
  for (const v of votes) {
    parts.push(`\n── ${v.model} ──`);
    if (v.reason) parts.push('Reason: ' + v.reason);
    if (v.chart_analysis && typeof v.chart_analysis === 'object') {
      const ca = v.chart_analysis;
      parts.push('Chart: ' + (ca.visual_trend || '') + ' · levels: ' + (ca.key_levels_seen || '') + ' · pattern: ' + (ca.pattern_at_price || ''));
    }
    if (v.analysis && typeof v.analysis === 'object') {
      for (const [k, val] of Object.entries(v.analysis)) if (val) parts.push(`${k}: ${val}`);
    }
    if (v.chain_of_thought && typeof v.chain_of_thought === 'object') {
      parts.push('Chain-of-thought:');
      for (const [k, val] of Object.entries(v.chain_of_thought)) if (val) parts.push(`  • ${val}`);
    }
  }
  return parts.join('\n');
}

function tfLabel(t) {
  if (t < 60) return t + 's';
  const m = t / 60;
  return m + 'm';
}

/* ── PAGE: LIVE CHART ── */
let liChart = null, liWs = null, liSeries = null, liTimer = null;
function renderLiveChart(view) {
  view.innerHTML = `
    <div class="live-layout">
      <div class="card">
        <h3>Live Settings</h3>
        <div class="field"><label>Asset</label>
          <select id="lc-asset" class="select">
            <option value="EURUSD_otc">EUR/USD (OTC)</option>
            <option value="GBPUSD_otc">GBP/USD (OTC)</option>
            <option value="USDJPY_otc">USD/JPY (OTC)</option>
            <option value="AUDUSD_otc">AUD/USD (OTC)</option>
            <option value="USDCHF_otc">USD/CHF (OTC)</option>
            <option value="EURGBP_otc">EUR/GBP (OTC)</option>
            <option value="USDCAD_otc">USD/CAD (OTC)</option>
            <option value="GBPUSD">GBP/USD</option>
            <option value="EURUSD">EUR/USD</option>
          </select>
        </div>
        <div class="field"><label>Timeframe</label>
          <select id="lc-tf" class="select">
            <option value="15">15s</option><option value="30">30s</option>
            <option value="60" selected>1m</option><option value="120">2m</option>
            <option value="300">5m</option><option value="900">15m</option>
          </select>
        </div>
        <button id="lc-connect" class="btn btn-primary btn-block">Connect</button>
        <div class="live-price" id="lc-price">—</div>
        <div class="live-status"><span class="dot red"></span><span id="lc-status">disconnected</span></div>
        <a class="btn btn-ghost btn-block" style="margin-top:14px" href="#/signals/llm">▶ Get Signal on this pair</a>
      </div>
      <div class="card chart-panel"><div id="live-chart"></div></div>
    </div>`;

  document.getElementById('lc-connect').onclick = startLiveChart;
  startLiveChart_cleanup();
  // simplest: connect immediately
  startLiveChart();
}

function startLiveChart_cleanup() {
  if (liWs) { try { liWs.close(); } catch (e) {} liWs = null; }
  if (liTimer) { clearInterval(liTimer); liTimer = null; }
  if (liChart) { liChart.remove(); liChart = null; liSeries = null; }
}

async function startLiveChart() {
  startLiveChart_cleanup();
  const asset = document.getElementById('lc-asset').value;
  const tf = parseInt(document.getElementById('lc-tf').value, 10);
  const el = document.getElementById('live-chart');
  const priceEl = document.getElementById('lc-price');
  const statusEl = document.getElementById('lc-status');
  const dot = document.querySelector('.live-status .dot');

  el.innerHTML = '<div class="empty">connecting…</div>';
  try {
    liChart = LightweightCharts.createChart(el, {
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: State.theme === 'dark' ? '#9CA3AF' : '#475569' },
      grid: { vertLines: { color: 'rgba(128,128,128,0.1)' }, horzLines: { color: 'rgba(128,128,128,0.1)' } },
      timeScale: { timeVisible: true, secondsVisible: true },
      width: el.clientWidth, height: 520,
    });
    liSeries = liChart.addCandlestickSeries({
      upColor: '#10B981', downColor: '#F43F5E', borderUpColor: '#10B981', borderDownColor: '#F43F5E',
      wickUpColor: '#10B981', wickDownColor: '#F43F5E',
    });
    new ResizeObserver(() => liChart.applyOptions({ width: el.clientWidth })).observe(el);
  } catch (e) { el.innerHTML = '<div class="empty">Chart lib failed</div>'; return; }

  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
  const url = `${proto}${location.host}/api/live`;
  try {
    liWs = new WebSocket(url);
  } catch (e) { toast('WS failed', 'error'); return; }
  liWs.onopen = () => {
    liWs.send(JSON.stringify({ type: 'subscribe', asset, timeframe: tf }));
    statusEl.textContent = 'connecting…';
    dot.className = 'dot red';
  };
  liWs.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'candles') {
        const data = (msg.candles || []).map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close }));
        liSeries.setData(data);
        statusEl.textContent = 'connected — live';
        dot.className = 'dot green';
      } else if (msg.type === 'tick') {
        if (liSeries) {
          const t = { time: msg.time, open: msg.price, high: msg.price, low: msg.price, close: msg.price };
          liSeries.update(t);
        }
        priceEl.textContent = msg.price.toFixed(5);
        priceEl.className = 'live-price';
        statusEl.textContent = `live · ${asset} @ ${tf}s`;
        dot.className = 'dot green';
      } else if (msg.type === 'status') {
        statusEl.textContent = msg.msg || '';
      }
    } catch (e) {}
  };
  liWs.onclose = () => { statusEl.textContent = 'disconnected'; dot.className = 'dot red'; };
  liWs.onerror = () => { statusEl.textContent = 'ws error'; dot.className = 'dot red'; };
}

/* ── PAGE: HISTORY ── */
async function renderHistory(view) {
  const signals = await api('/signals?limit=50');
  const rows = signals.map(s => `
    <tr data-signal-id="${s.id}" class="signal-row" style="cursor:pointer">
      <td><b>${esc(s.pair)}</b></td>
      <td>${esc(s.tf_label)}</td>
      <td>${s.model_type.toUpperCase()}</td>
      <td><span class="stat-badge ${s.direction === 'BUY' ? 'badge-buy' : s.direction === 'SELL' ? 'badge-sell' : 'badge-skip'}">${esc(s.direction) || 'SKIP'}</span></td>
      <td>${s.confidence}%</td>
      <td>${s.status}</td>
      <td>${s.math_score} / 10</td>
      <td>-${s.credits_cost} ⚡</td>
      <td>${fmtDT(s.created_at)}</td>
    </tr>`).join('') || '<tr><td colspan="9" class="empty">No signals yet</td></tr>';

  view.innerHTML = `
    <div class="card">
      <h3>🗂️ Signal History</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Pair</th><th>TF</th><th>Model</th><th>Direction</th><th>Conf</th><th>Status</th><th>Math</th><th>Cost</th><th>Time</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>
    <div id="detail-slot"></div>`;

  view.querySelectorAll('.signal-row').forEach(tr => {
    tr.onclick = async () => {
      const detail = await api('/signal_detail/' + tr.dataset.signalId);
      const slot = document.getElementById('detail-slot');
      const votes = detail.votes || [];
      const voteRows = votes.map(v => `
        <div class="vote-row"><div class="vote-model">${esc(v.model)}</div>
          <div style="flex:1"></div>
          <div><span class="vote-sign ${v.sign === 'BUY' ? 'buy' : v.sign === 'SELL' ? 'sell' : ''}">${v.sign}</span></div>
          <div class="vote-conf">${v.confidence}%</div></div>`).join('');
      slot.innerHTML = `
        <div class="result-card">
          <div class="result-pair"><b>${esc(detail.pair)}</b> ${detail.original_pair !== detail.pair ? '→ ' + esc(detail.original_pair) : ''} · ${esc(detail.tf_label)} · ${detail.model_type.toUpperCase()}</div>
          <div class="result-direction ${detail.direction === 'BUY' ? 'buy' : 'sell'}" style="${detail.status !== 'done' ? 'color:var(--text-2);font-size:24px' : ''}">${detail.status === 'done' ? (detail.direction === 'BUY' ? '▲ BUY' : '▼ SELL') : '⏭️ ' + detail.status} ${detail.status === 'done' ? '<span class="result-confidence">' + detail.confidence + '%</span>' : ''}</div>
          <div class="vote-list">${voteRows || '<div class="empty">no votes</div>'}</div>
          <div class="reasoning-panel"><div class="reasoning-box" style="white-space:pre-wrap;color:var(--text-2);font-size:13px">${esc(detail.reason || '')}</div></div>
          ${detail.chart_b64 ? `<div class="chart-img"><img src="data:image/png;base64,${detail.chart_b64}" /></div>` : ''}
        </div>`;
      slot.scrollIntoView({ behavior: 'smooth' });
    };
  });
}

/* ── PAGE: CREDITS ── */
async function renderCredits(view) {
  const user = State.user;
  const data = await api('/credits');
  const rows = (data.ledger || []).slice(0, 50).map(t => `
    <tr>
      <td class="${t.amount >= 0 ? '' : ''}">${t.amount >= 0 ? '<span class="stat-badge badge-buy">+' + t.amount + '</span>' : '<span class="stat-badge badge-sell">' + t.amount + '</span>'}</td>
      <td>${esc(t.reason)}</td>
      <td>${fmtDT(t.created_at)}</td>
    </tr>`).join('');

  view.innerHTML = `
    <div class="grid grid-3">
      <div class="card"><div class="kpi-label">Balance</div>
        <div class="kpi-value" style="color:var(--accent-2)">${Math.round(data.balance)} ⚡</div></div>
      <div class="card"><div class="kpi-label">Plan</div>
        <div class="kpi-value" style="font-size:24px">${esc(user.plan)}</div>
        <div class="kpi-sub">${user.plan_credits_per_month ? user.plan_credits_per_month + ' credits / month' : '—'}</div></div>
      <div class="card"><div class="kpi-label">Renews</div>
        <div class="kpi-value" style="font-size:20px">${fmtDT(user.renews_at)}</div>
        <div class="kpi-sub">${user.plan_price ? '$' + user.plan_price + '/mo' : 'Free trial'}</div></div>
    </div>
    <div class="grid grid-2" style="grid-template-columns:1fr 2fr">
      <div class="card">
        <h3>💎 Upgrade</h3>
        <p style="color:var(--text-2);font-size:13px;margin-bottom:14px">Need more signals? Grab a subscription for monthly credits.</p>
        <a class="btn btn-primary btn-block" href="#/pricing">View Plans</a>
      </div>
      <div class="card">
        <h3>🧾 Transaction Ledger</h3>
        <div class="table-wrap"><table>
          <thead><tr><th>Amount</th><th>Reason</th><th>Time</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </div>
    </div>`;
}

/* ── PAGE: PRICING ── */
async function renderPricing(view) {
  const plans = await api('/plans');
  const current = State.user ? State.user.plan : 'FREE';
  const cards = plans.map(p => `
    <div class="plan-card ${p.id === 'pro' ? 'popular' : ''}">
      ${p.id === 'pro' ? '<div class="popular-tag">⭐ MOST POPULAR</div>' : ''}
      <div class="plan-name">${esc(p.name)}</div>
      <div class="plan-price">$${p.price}<span>/mo</span></div>
      <div class="plan-period">${p.credits_per_month.toLocaleString()} credits / month</div>
      <ul class="plan-features">${p.features.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
      ${p.price === 0
        ? `<button data-free="1" class="btn btn-ghost btn-block" ${current === 'FREE' ? 'disabled' : ''}>${current === 'FREE' ? 'Current Plan' : 'Free Plan'}</button>`
        : `<button class="btn ${p.id === 'pro' ? 'btn-buy' : 'btn-primary'} btn-block" data-plan="${p.id}">Upgrade to ${esc(p.name)}</button>`}
    </div>`).join('');

  view.innerHTML = `
    <div class="plans-grid">${cards}</div>
    <p style="text-align:center;color:var(--text-3);font-size:12px;margin-top:14px">10 credits per signal · unused Pro credits roll over within the month</p>`;

  view.querySelectorAll('[data-plan],[data-free]').forEach(b => {
    b.onclick = async () => {
      if (b.dataset.free) {
        toast('You are on the FREE plan — enjoy your 120 credits!', 'ok');
        return;
      }
      try {
        const chk = await api('/checkout', { method: 'POST', body: { plan_id: b.dataset.plan } });
        if (chk.mode === 'stripe' && chk.url) { location.href = chk.url; }
        else if (chk.mode === 'mock') {
          await api('/checkout/mock/complete', { method: 'POST', body: { plan_id: b.dataset.plan } });
          toast('Plan activated (mock checkout) — credits added!', 'ok');
          setTimeout(() => location.reload(), 1100);
        }
      } catch (e) { toast(e.message, 'error'); }
    };
  });
}

window.router = router;