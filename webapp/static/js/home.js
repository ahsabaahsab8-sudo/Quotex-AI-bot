/* ── Quotex AI Home — real data wiring ───────────────────────────────
 * Reads /api/me (credits + plan), /api/signals (recent signals) and
 * streams real BTC/USD candles over the /api/live websocket.
 */
(function () {
  'use strict';

  var BTCD_TIMEFRAME = 60;       // 1m candles
  var BTCO_ASSET = 'BTCUSD_otc'; // Quotex crypto code
  var VISIBLE_CANDLES = 5;

  var chart = null, series = null, ws = null, wsTimer = null;
  var cachedCandles = [];
  var lastBucket = 0;
  var started = false;

  function run() {
    bindStaticButtons();
    if (started) return;
    started = true;
    renderHeader();
    refreshSignals();
    startLiveChart();
  }

  /* ── header / credits ── */
  function renderHeader() {
    var user = App.user || {};
    var el = document.getElementById('credit-balance');
    if (el) el.textContent = nf(Math.round(user.credits || 0));

    var g = document.getElementById('greeting');
    if (g) {
      var h = new Date().getHours();
      g.textContent = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
    }

    var plan = String(user.plan || 'FREE').toUpperCase();
    var planLabel = plan === 'FREE' ? 'Free Plan' : plan === 'STARTER' ? 'Starter Plan' : 'Pro Plan';
    var renew = user.renews_at ? 'renews ' + shortDate(user.renews_at) : '';
    var pl = document.getElementById('plan-line');
    if (pl) pl.textContent = planLabel + (renew ? ' • ' + renew : '');

    var img = document.getElementById('user-avatar');
    if (img) {
      if (user.avatar) img.src = user.avatar;
      img.onerror = showAvatarFallback;
      if (!user.avatar) showAvatarFallback();
    }
  }

  function showAvatarFallback() {
    var img = document.getElementById('user-avatar');
    if (img) img.classList.add('hidden');
    var fb = document.getElementById('avatar-fallback');
    if (fb) { fb.classList.remove('hidden'); fb.classList.add('flex'); }
  }

  /* ── stats ── */
  function renderStats(signals) {
    var done = (signals || []).filter(function (s) { return s.status === 'done'; });
    var wins = done.filter(function (s) { return s.direction === 'BUY'; });

    var winrate = done.length ? Math.round(wins.length / done.length * 100) : 0;
    var ring = document.getElementById('winrate-ring');
    if (ring) ring.setAttribute('stroke-dasharray', Math.max(0, Math.min(100, winrate)) + ', 100');
    var wn = document.getElementById('winrate-num');
    if (wn) wn.textContent = done.length ? winrate + '%' : '—';

    var confs = done.map(function (s) { return parseFloat(s.confidence); }).filter(function (v) { return !isNaN(v) && v > 0; });
    var avg = confs.length ? Math.round(confs.reduce(function (a, b) { return a + b; }, 0) / confs.length) : null;
    var cn = document.getElementById('conf-num');
    if (cn) cn.textContent = avg != null ? avg + '%' : '—';
    var sub = document.getElementById('conf-sub');
    if (sub) sub.innerHTML = '<span class="material-symbols-outlined text-[14px]">insights</span>' +
      esc(done.length ? done.length + ' signals analyzed' : 'no completed signals yet');
  }

  /* ── recent signals ── */
  async function refreshSignals() {
    var wrap = document.getElementById('signals-list');
    if (!wrap) return;
    try {
      var signals = await api('/signals?limit=8');
      renderStats(signals);
      if (!signals.length) {
        wrap.innerHTML = '<div class="card-sheen rounded-lg p-6 text-center text-on-surface-variant text-[13px]">' +
          'No signals yet — press <b class="text-primary-container">Get AI Signal</b> to run your first one.</div>';
      } else {
        wrap.innerHTML = signals.slice(0, 5).map(signalRow).join('');
      }
    } catch (e) {
      wrap.innerHTML = '<div class="card-sheen rounded-lg p-6 text-center text-on-surface-variant text-[13px]">Could not load signals.</div>';
    }
  }

  function signalRow(s) {
    var dir = String(s.direction || 'SKIP').toUpperCase();
    var conf = parseFloat(s.confidence) || 0;

    var pill, border;
    if (dir === 'BUY') {
      pill = 'bg-[#4ade80]/10 text-[#4ade80] border-[#4ade80]/20';
      border = 'border-l-[#4ade80]';
    } else if (dir === 'SELL') {
      pill = 'bg-error/10 text-error border-error/20';
      border = 'border-l-error';
    } else {
      pill = 'bg-[#facc15]/10 text-[#facc15] border-[#facc15]/20';
      border = 'border-l-[#facc15]';
    }
    var dirLabel = dir + (dir !== 'SKIP' && conf ? ' ' + conf.toFixed(0) + '%' : '');

    return '<div class="card-sheen rounded-lg p-3 flex justify-between items-center transition-colors cursor-pointer border-l-2 ' + border + '">' +
      '<div class="flex items-center gap-3">' +
      '<div class="w-10 h-10 rounded-full bg-[#1A1A1A] flex items-center justify-center border border-[#2A2A2A]">' +
      '<span class="material-symbols-outlined text-white opacity-80 text-[20px]">' + rowIcon(s.pair) + '</span></div>' +
      '<div><h4 class="font-bold text-white text-[15px]">' + esc(s.pair) + '</h4>' +
      '<p class="text-on-surface-variant text-[11px] font-mono">' + esc(s.tf_label || '') + ' · ' + esc(s.model_type || '') + '</p>' +
      (s.trade_time ? '<p class="text-on-surface-variant text-[10px] font-mono">Trade ' + esc(s.trade_time) + ' PKT</p>' : '') +
      '</div>' +
      '</div>' +
      '<div class="text-right">' +
      '<div class="' + pill + ' px-2 py-0.5 rounded text-[12px] font-bold mb-1 border inline-block">' +
      esc(dirLabel) + '</div>' +
      '<div class="flex items-center justify-end gap-1.5">' +
      tradeResultBadge(s) +
      '<p class="text-on-surface-variant text-[10px] opacity-70">' + ago(s.created_at) + '</p></div></div></div>';
  }

  function tradeResultBadge(s) {
    var r = (s.trade_result || '').toUpperCase();
    if (r === 'WIN')
      return '<span class="text-[10px] font-bold text-[#4ade80] bg-[#4ade80]/10 border border-[#4ade80]/20 rounded px-1.5 py-0.5">WIN</span>';
    if (r === 'LOSS')
      return '<span class="text-[10px] font-bold text-error bg-error/10 border border-error/20 rounded px-1.5 py-0.5">LOSS</span>';
    return '<span class="text-[10px] font-bold text-on-surface-variant opacity-60 rounded px-1.5 py-0.5">' +
      (r ? esc(r) : '…') + '</span>';
  }

  function rowIcon(pair) {
    var p = String(pair || '').toUpperCase();
    var cryptoChecks = ['BTC', 'ETH', 'XRP', 'DOGE', 'SOL', 'LTC', 'BCH', 'LINK', 'ADA', 'TRX', 'DOT', 'XBT', 'MATIC', 'TON', 'AVAX', 'ZEC', 'DASH', 'LUN'];
    for (var i = 0; i < cryptoChecks.length; i++) {
      if (p.indexOf(cryptoChecks[i]) !== -1) return 'currency_bitcoin';
    }
    return 'currency_exchange';
  }

  /* ── live BTC/USD chart ── */
  function startLiveChart() {
    if (!window.LightweightCharts) {
      var sig = document.getElementById('market-signal');
      if (sig) sig.innerHTML = '<span class="text-[10px] font-bold text-on-surface-variant">offline</span>';
      return;
    }
    var el = document.getElementById('live-chart-area');
    if (!el) return;

    chart = LightweightCharts.createChart(el, {
      layout: { background: { type: 'solid', color: '#141414' }, textColor: '#d1c6ab', fontSize: 10 },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      timeScale: { timeVisible: true, secondsVisible: false, borderVisible: false },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.1, bottom: 0.1 } },
      autoSize: true,
      height: 128,
      crosshair: { mode: 0 },
    });
    series = chart.addCandlestickSeries({
      upColor: '#4ade80', downColor: '#ff6b6b',
      borderUpColor: '#4ade80', borderDownColor: '#ff6b6b',
      wickUpColor: '#4ade80', wickDownColor: '#ff6b6b',
    });

    if (window.ResizeObserver) {
      new ResizeObserver(function () {
        chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
      }).observe(el.parentElement);
    }

    connectLive();
  }

  function connectLive() {
    clearTimeout(wsTimer);
    var proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    ws = new WebSocket(proto + location.host + '/api/live');
    ws.onopen = function () { ws.send(JSON.stringify({ type: 'subscribe', asset: BTCO_ASSET, timeframe: BTCD_TIMEFRAME })); };
    ws.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg.type === 'candles') setCandles(msg.candles || []);
      else if (msg.type === 'tick') onTick(msg);
    };
    ws.onclose = function () { wsTimer = setTimeout(connectLive, 4000); };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }

  function setCandles(candles) {
    if (!candles.length) return;
    cachedCandles = candles.slice(-VISIBLE_CANDLES - 1);
    lastBucket = cachedCandles[cachedCandles.length - 1].time;
    series.setData(cachedCandles.map(cleanCandle));
    fitVisible();
  }

  function onTick(t) {
    var price = parseFloat(t.price);
    if (!price || !series) return;
    var bucket = Math.floor(parseFloat(t.time) / BTCD_TIMEFRAME) * BTCD_TIMEFRAME;

    if (cachedCandles.length && bucket === lastBucket) {
      var last = cachedCandles[cachedCandles.length - 1];
      last.close = price;
      last.high = Math.max(last.high, price);
      last.low = Math.min(last.low, price);
    } else if (bucket > lastBucket) {
      cachedCandles.push({ time: bucket, open: price, high: price, low: price, close: price });
      if (cachedCandles.length > VISIBLE_CANDLES + 1) cachedCandles.shift();
      lastBucket = bucket;
    } else {
      return;
    }
    series.setData(cachedCandles.map(cleanCandle));
    fitVisible();
    showSignal();
  }

  function fitVisible() {
    var n = cachedCandles.length;
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - VISIBLE_CANDLES), to: n });
  }

  function cleanCandle(c) {
    return { time: parseInt(c.time, 10), open: c.open, high: c.high, low: c.low, close: c.close };
  }

  function showSignal() {
    var last = cachedCandles[cachedCandles.length - 1];
    var el = document.getElementById('market-signal');
    if (!last || !el) return;
    var color, icon, label;
    if (last.close >= last.open) { label = 'BUY'; color = '#4ade80'; icon = 'arrow_drop_up'; }
    else { label = 'SELL'; color = '#ff6b6b'; icon = 'arrow_drop_down'; }
    el.innerHTML = '<div class="flex flex-col items-center animate-bounce">' +
      '<span class="text-[9px] font-bold px-1 rounded" style="background:' + color + '22;color:' + color + '">' + label + '</span>' +
      '<span class="material-symbols-outlined text-[14px]" style="color:' + color + ';font-variation-settings:\'FILL\' 1">' + icon + '</span></div>';
  }

  /* ── static buttons ── */
  function bindStaticButtons() {
    var gs = document.getElementById('btn-getsignal');
    if (gs && !gs.dataset.bound) {
      gs.dataset.bound = '1';
      gs.addEventListener('click', function () { App.show('signals'); });
    }
    bindOnce('btn-topup', function () { toast('Upgrade & billing arrive with the “You” menu', 'info'); });
    bindOnce('btn-notify', function () { toast('No new alerts', 'info'); });
    bindOnce('btn-settings', function () { toast('Settings move to the “You” menu', 'info'); });
  }

  function bindOnce(id, fn) {
    var el = document.getElementById(id);
    if (el && !el.dataset.bound) { el.dataset.bound = '1'; el.addEventListener('click', fn); }
  }

  /* shared helpers exposed for the signals page */
  window.ux = {
    refreshHomeSignals: refreshSignals,
    signalRow: signalRow,
    ago: ago,
  };

  /* ── helpers ── */
  function nf(n) { return Number(n).toLocaleString('en-US'); }
  function shortDate(iso) {
    var d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
  function ago(iso) {
    if (!iso) return '';
    var s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return Math.round(s / 60) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' h ago';
    return Math.round(s / 86400) + ' d ago';
  }
  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  App.register('home', { run: run });
})();