/* ── Quotex AI Signals — build & run a real AI signal ────────────────
 * Timeframes come from /api/timeframes (same as the bot).
 * Asset pairs come live from Quotex (/api/pairs) filtered by category
 * (All / OTC / Standard / Crypto) with real payout %.
 * "Get Signal" enqueues a job and shows the live 5-step pipeline, then
 * renders the BUY / SELL result + per-model reasoning in the gold design.
 */
(function () {
  'use strict';

  var MODE_COST = { llm: 10, vision: 10, all: 20 };
  var CAT_KEY = { all: 'all', OTC: 'OTC', REAL: 'REAL', CRYPTO: 'CRYPTO' };
  var CAT_FULL = { all: 'All', OTC: 'OTC', REAL: 'Standard', CRYPTO: 'Crypto' };
  var TF_LABEL = { 15: '15s', 30: '30s', 60: '1m', 120: '2m', 300: '5m', 900: '15m', 1800: '30m', 3600: '1h' };
  var STEPS = [
    'Connect to Quotex',
    'Fetch market data + indicators',
    'Analyze market',
    'News + chart check',
    'AI vote pipeline',
  ];
  var SHORT = {
    'Gemini Flash': 'Gemini',
    'Nemotron 3 Nano': 'Nano',
    'Dots3-Note': 'Dots',
    'Nemotron 3 Ultra': 'Nemotron',
    'Llama 3.1 8B': 'Llama8B',
    'Laguna-S 2.1': 'Laguna',
  };

  var state = { mode: 'vision', cat: 'all', tf: 60, pair: null, pairLabel: '' };
  var pairsCache = null;
  var timeframes = [];
  var countdownTimer = null;
  var tradePollTimer = null;

  var SEG_ACTIVE = 'flex-1 py-2 text-center text-label-mono font-label-mono text-primary-container font-bold bg-surface-container-highest rounded-md shadow-sm border border-surface-container-high';
  var SEG_IDLE = 'flex-1 py-2 text-center text-label-mono font-label-mono text-on-surface-variant rounded-md hover:bg-surface-container-highest transition-colors';
  var CHIP_ACTIVE = 'px-4 py-2 rounded-full border border-primary-container bg-primary-container/10 text-label-mono font-label-mono text-primary-container whitespace-nowrap font-bold';
  var CHIP_IDLE = 'px-4 py-2 rounded-full border border-surface-container-high text-label-mono font-label-mono text-on-surface-variant whitespace-nowrap hover:border-primary-container transition-colors';
  var TF_ACTIVE = 'py-2 rounded-lg bg-primary-container text-black font-bold text-label-mono font-label-mono border border-primary-container';
  var TF_IDLE = 'py-2 rounded-lg bg-background border border-surface-container-high text-on-surface-variant hover:border-primary-container transition-colors text-label-mono font-label-mono';

  App.register('signals', { run: run });

  function run() {
    bindSegmented();
    bindCatChips();
    bindPairButton();
    bindGo();
    if (!timeframes.length) loadTimeframes();
    loadPairs();
    setCost();
  }

  /* ── model type segmented control ── */
  function bindSegmented() {
    document.querySelectorAll('.mod-btn').forEach(function (b) {
      if (b.dataset.bound) return;
      b.dataset.bound = '1';
      b.addEventListener('click', function () {
        state.mode = b.dataset.mode;
        document.querySelectorAll('.mod-btn').forEach(function (x) {
          x.className = 'mod-btn ' + (x === b ? SEG_ACTIVE : SEG_IDLE);
        });
        setCost();
      });
    });
  }

  /* ── category chips → pair list ── */
  function bindCatChips() {
    document.querySelectorAll('.cat-chip').forEach(function (b) {
      if (b.dataset.bound) return;
      b.dataset.bound = '1';
      b.addEventListener('click', function () {
        state.cat = b.dataset.cat;
        document.querySelectorAll('.cat-chip').forEach(function (x) {
          x.className = 'cat-chip ' + (x === b ? CHIP_ACTIVE : CHIP_IDLE);
        });
        renderPairList(state.cat);
        var first = currentPairs()[0];
        if (first) selectPair(first.symbol, first.label, first.payout);
      });
    });
  }

  /* ── asset pair button + dropdown ── */
  function bindPairButton() {
    var btn = document.getElementById('sig-pair-btn');
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', function () {
      var list = document.getElementById('sig-pair-list');
      list.classList.toggle('hidden');
      if (list.children.length === 0) renderPairList(state.cat);
    });
  }

  function currentPairs() {
    var p = pairsCache || {};
    if (state.cat === 'all') {
      return [].concat(p.OTC || [], p.REAL || [], p.CRYPTO || [])
        .sort(function (a, b) { return (b.payout || 0) - (a.payout || 0); });
    }
    return (p[state.cat] || []);
  }

  async function loadPairs() {
    var list = document.getElementById('sig-pair-list');
    var label = document.getElementById('sig-pair-label');
    try {
      pairsCache = await api('/pairs');
      var items = currentPairs();
      if (items.length) {
        var first = items[0];
        selectPair(first.symbol, first.label, first.payout);
      } else if (label) {
        label.textContent = pairsCache.error ? 'Pair fetch failed' : 'No pairs active';
      }
      if (list && !list.classList.contains('hidden')) renderPairList(state.cat);
    } catch (e) {
      if (label) label.textContent = 'Could not load pairs';
      if (list) list.innerHTML = '<div class="px-3 py-4 text-center text-on-surface-variant text-[12px]">' +
        'Could not load pairs — check Quotex connection.</div>';
    }
  }

  function renderPairList(cat) {
    var list = document.getElementById('sig-pair-list');
    if (!list) return;
    if (!pairsCache) {
      list.innerHTML = '<div class="px-3 py-4 text-center text-on-surface-variant text-[12px]">' +
        (list.classList.contains('hidden') ? 'Select a category then tap here to load pairs…' : 'No pairs — check Quotex connection') + '</div>';
      return;
    }
    var items = currentPairs();
    if (!items.length) {
      list.innerHTML = '<div class="px-3 py-4 text-center text-on-surface-variant text-[12px]">No ' + CAT_FULL[cat] + ' pairs active right now.</div>';
      return;
    }
    list.innerHTML = items.slice(0, 400).map(function (p) {
      var icon = isCrypto(p.symbol) ? 'currency_bitcoin' : 'currency_exchange';
      var sel = p.symbol === state.pair;
      return '<button data-symbol="' + esc(p.symbol) + '" data-label="' + esc(p.label) + '" data-payout="' + esc(p.payout) + '" ' +
        'class="pair-item w-full flex justify-between items-center px-3 py-2.5 text-left border-b border-surface-container-high/50 ' +
        (sel ? 'bg-surface-container' : 'hover:bg-surface-container') + ' transition-colors">' +
        '<span class="flex items-center gap-3">' +
        '<span class="material-symbols-outlined text-[16px] text-primary-container">' + icon + '</span>' +
        '<span class="text-[13px] font-bold text-white">' + esc(p.label) + '</span></span>' +
        '<span class="text-[11px] font-label-mono font-bold text-primary-container bg-primary-container/10 border border-primary-container/30 px-1.5 py-0.5 rounded">' +
        (p.payout != null ? p.payout + '%' : '') + '</span></button>';
    }).join('');

    list.querySelectorAll('.pair-item').forEach(function (item) {
      item.addEventListener('click', function () {
        selectPair(item.dataset.symbol, item.dataset.label, parseInt(item.dataset.payout, 10) || null);
        list.classList.add('hidden');
      });
    });
  }

  function selectPair(symbol, label, payout) {
    state.pair = symbol;
    state.pairLabel = label;
    var el = document.getElementById('sig-pair-label');
    if (el) el.textContent = payout != null ? label + ' · ' + payout + '%' : label;
  }

  function setPairLabel(text) {
    var el = document.getElementById('sig-pair-label');
    if (el) el.textContent = text;
  }

  /* ── timeframes (from /api/timeframes = bot's set) ── */
  async function loadTimeframes() {
    try {
      var data = await api('/timeframes');
      timeframes = data.timeframes || [];
    } catch (e) { timeframes = [15, 30, 60, 120, 300, 900, 1800, 3600]; }
    buildTfChips();
  }

  function buildTfChips() {
    var wrap = document.getElementById('sig-tf');
    if (!wrap) return;
    wrap.innerHTML = timeframes.map(function (tf) {
      return '<button data-tf="' + tf + '" class="tf-chip ' + (tf === state.tf ? TF_ACTIVE : TF_IDLE) + '">' + (TF_LABEL[tf] || tf + 's') + '</button>';
    }).join('');
    wrap.querySelectorAll('.tf-chip').forEach(function (b) {
      b.addEventListener('click', function () {
        state.tf = parseInt(b.dataset.tf, 10);
        wrap.querySelectorAll('.tf-chip').forEach(function (x) {
          x.className = 'tf-chip ' + (x === b ? TF_ACTIVE : TF_IDLE);
        });
      });
    });
  }

  /* ── cost + get signal ── */
  function setCost() {
    var c = MODE_COST[state.mode] || 10;
    var el = document.getElementById('sig-cost');
    if (el) el.textContent = 'Costs ' + c + ' credits · auto-refund if no signal';
    var t = document.getElementById('sig-go-text');
    if (t) t.textContent = 'Get Signal · ' + c + ' ⚡';
  }

  function bindGo() {
    var btn = document.getElementById('btn-sig-go');
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', go);
  }

  async function go() {
    var btn = document.getElementById('btn-sig-go');
    var txt = document.getElementById('sig-go-text');
    if (!state.pair) { toast('Pick an asset pair first', 'error'); return; }
    btn.disabled = true;
    if (txt) txt.textContent = 'Running…';
    hideResult();
    showPipeline();
    try {
      var job = await api('/signal', {
        method: 'POST',
        body: { pair: state.pair, timeframe_seconds: state.tf, model_type: state.mode },
      });
      await pollJob(job.job_id);
    } catch (e) {
      toast(e.message, 'error');
      hidePipeline();
    } finally {
      btn.disabled = false;
      if (txt) txt.textContent = 'Get Signal · ' + (MODE_COST[state.mode] || 10) + ' ⚡';
    }
  }

  /* ── live pipeline ── */
  function showPipeline() {
    var card = document.getElementById('sig-pipeline');
    if (card) card.classList.remove('hidden');
    var wrap = document.getElementById('sig-pipe-steps');
    if (!wrap) return;
    wrap.innerHTML = STEPS.map(function (label, i) {
      return '<div class="step-row flex items-center gap-3 p-3 rounded-lg bg-background/70 border border-surface-container-high">' +
        '<div class="step-num w-7 h-7 rounded-md flex items-center justify-center text-[12px] font-bold bg-surface-container text-on-surface-variant shrink-0">' + (i + 1) + '</div>' +
        '<div class="flex-1 min-w-0"><div class="step-title text-[13px] font-bold text-white">' + label + '</div>' +
        '<div class="step-detail text-[11px] text-on-surface-variant truncate">…</div></div>' +
        '<div class="step-state text-[12px] text-on-surface-variant shrink-0"></div></div>';
    }).join('');
  }

  function hidePipeline() {
    var card = document.getElementById('sig-pipeline');
    if (card) card.classList.add('hidden');
  }

  function hideResult() {
    var r = document.getElementById('sig-result');
    if (r) r.innerHTML = '';
    clearCountdown();
    clearTradePoll();
  }

  async function pollJob(jobId) {
    var wrap = document.getElementById('sig-pipe-steps');
    var statusEl = document.getElementById('pipe-status');
    var rows = wrap ? Array.prototype.slice.call(wrap.children) : [];
    var lastDetail = '';
    var done = false;

    var refresh = async function () {
      var j = await api('/signal/' + jobId);
      var step = Math.max(1, j.step || 1);
      var running = j.status === 'running';

      rows.forEach(function (row, i) {
        var isDone = !running && i < rows.length; // handled below
        var doneState = j.status !== 'running' || i < step - 1;
        var activeState = running && i === step - 1;
        row.classList.toggle('active', activeState);
        row.classList.toggle('border-primary-container/60', activeState);

        var num = row.querySelector('.step-num');
        if (num) {
          num.textContent = doneState ? '✓' : (i + 1);
          num.className = 'step-num w-7 h-7 rounded-md flex items-center justify-center text-[12px] font-bold shrink-0 ' +
            (doneState ? 'bg-primary-container text-black' : activeState ? 'bg-primary-container/20 border border-primary-container text-primary-container' : 'bg-surface-container text-on-surface-variant');
        }
        var st = row.querySelector('.step-state');
        if (st) st.innerHTML = doneState ? '<span class="text-primary-container text-[13px] font-bold">✓</span>' : activeState ? '<span class="spinner"></span>' : '';
        if (activeState) {
          var d = row.querySelector('.step-detail');
          if (d) d.textContent = j.progress_text || 'working…';
          lastDetail = j.progress_text || '';
        }
      });

      if (statusEl) {
        statusEl.textContent = running ? 'step ' + step + '/5' : j.status;
      }
      if (j.status !== 'running') {
        rows.forEach(function (row, i) {
          row.classList.remove('active');
          var num = row.querySelector('.step-num');
          if (num) {
            num.textContent = '✓';
            num.className = 'step-num w-7 h-7 rounded-md flex items-center justify-center text-[12px] font-bold shrink-0 bg-primary-container text-black';
          }
          var st = row.querySelector('.step-state');
          if (st) st.innerHTML = '<span class="text-primary-container text-[13px] font-bold">✓</span>';
          if (i === rows.length - 1) {
            var d = row.querySelector('.step-detail');
            if (d && j.progress_text) d.textContent = j.progress_text;
          }
        });
        if (j.status === 'failed') toast('Signal failed: ' + (j.error || 'unknown'), 'error');
        else renderResult(j.result || {}, j.status);
        refreshRecent();
        if (window.ux && ux.refreshHomeSignals) ux.refreshHomeSignals();
        return true;
      }
      return false;
    };

    await refresh();
    var timer = setInterval(async function () {
      try {
        if (await refresh()) clearInterval(timer);
      } catch (e) { clearInterval(timer); toast(e.message, 'error'); }
    }, 2500);
    setTimeout(function () { clearInterval(timer); }, 6 * 60 * 1000);
  }

  /* ── result rendering ── */
  function renderResult(result, status) {
    var slot = document.getElementById('sig-result');
    if (!slot) return;
    clearCountdown();

    var dir = String(result.direction || 'SKIP').toUpperCase();
    var skipped = status === 'skipped' || result.skipped || dir === 'SKIP' || dir === 'NONE' || dir === 'NEUTRAL';

    if (skipped || !dir) {
      slot.innerHTML = '<div class="bg-card-gradient border border-surface-container-high rounded-xl p-6 glow-effect text-center">' +
        '<div class="text-[44px] leading-none"><span class="material-symbols-outlined text-[44px] text-on-surface-variant" style="font-variation-settings:\'FILL\' 1">skip_next</span></div>' +
        '<h3 class="text-headline-lg-mobile font-headline-lg-mobile text-on-surface-variant mt-3">No reliable signal</h3>' +
        '<p class="text-label-mono font-label-mono text-sm text-on-surface-variant mt-2">' + esc(result.reason || 'AI models determined no reliable trade on this pair right now.') + '</p>' +
        '<p class="text-[11px] text-on-surface-variant opacity-70 mt-4">Credits auto-refunded</p></div>';
      return;
    }

    var isBuy = dir === 'BUY';
    var arrow = isBuy ? 'arrow_upward' : 'arrow_downward';
    var color = isBuy ? '#facc15' : '#f87171';
    var votes = result.votes || [];
    var buyCount = votes.filter(function (v) { return v.sign === 'BUY'; }).length;
    var sellCount = votes.filter(function (v) { return v.sign === 'SELL'; }).length;

    var chips = votes.slice(0, 6).map(function (v) {
      var c = v.sign === 'BUY' ? '#34d399' : v.sign === 'SELL' ? '#f87171' : '#9a9078';
      return '<div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-container-high border border-surface-container-highest text-sm">' +
        '<span class="w-2 h-2 rounded-full" style="background:' + c + '"></span>' +
        '<span class="text-on-surface-variant text-[12px]">' + esc(shortName(v.model)) + '</span></div>';
    }).join('');

    slot.innerHTML =
      '<div class="bg-card-gradient border border-surface-container-high rounded-xl p-6 glow-effect relative overflow-hidden">' +
      '<div class="absolute -top-20 -right-20 w-64 h-64 bg-primary-container/5 rounded-full blur-3xl pointer-events-none"></div>' +
      '<div class="flex justify-between items-start mb-6">' +
      '<div><div class="text-label-mono font-label-mono text-on-surface-variant flex items-center gap-2">' +
      '<span>' + esc(result.pair || state.pairLabel || '') + '</span>' +
      '<span class="w-1 h-1 rounded-full bg-surface-container-high"></span><span>' + esc(result.tf_label || TF_LABEL[state.tf] || '') + '</span></div>' +
      '<div class="flex items-center gap-3 mt-2">' +
      '<h3 class="text-[48px] leading-none font-bold flex items-center" style="color:' + color + '">' +
      '<span class="material-symbols-outlined text-[40px] mr-2" style="font-variation-settings:\'FILL\' 1">' + arrow + '</span>' + dir + '</h3></div></div>' +
      '<div class="text-right"><div class="text-label-mono font-label-mono text-on-surface-variant">Confidence</div>' +
      '<div class="text-headline-lg-mobile font-headline-lg-mobile text-white">' + esc(result.confidence) + '%</div></div></div>' +
      '<div class="flex gap-2 flex-wrap mb-6">' + chips + '</div>' +
      '<div class="flex items-center justify-between p-3 rounded-lg bg-surface-container border border-primary-container/20">' +
      '<div class="flex items-center gap-2 text-primary-container">' +
      '<span class="material-symbols-outlined text-[18px]">timer</span>' +
      '<span class="text-label-mono font-label-mono font-bold" id="sig-countdown">Next candle closes in ' + remaining() + 's</span></div>' +
      '<button class="text-on-surface-variant hover:text-white"><span class="material-symbols-outlined text-[20px]">notifications_active</span></button></div>' +

      '<div class="flex items-center justify-between p-3 rounded-lg bg-background/70 border border-surface-container-high mt-2">' +
      '<div class="flex items-center gap-2 text-on-surface-variant text-label-mono font-label-mono text-xs">' +
      '<span class="material-symbols-outlined text-[18px]">swap_vert</span>Trade opens at <span class="text-white font-bold">' + esc(result.trade_time || '—') + '</span> PKT</div>' +
      '<div id="sig-trade-result">' + tradeBadge(result) + '</div></div>' +
      '</div>' +

      (result.chart_b64 ? '<div class="rounded-xl overflow-hidden border border-surface-container-high"><img src="data:image/png;base64,' + result.chart_b64 + '" class="w-full block" /></div>' : '') +

      '<div class="bg-card-gradient border border-surface-container-high rounded-xl p-5 flex flex-col gap-4 glow-effect">' +
      '<div class="border-b border-surface-container-high pb-3 flex justify-between items-center">' +
      '<h4 class="text-headline-lg-mobile font-headline-lg-mobile text-primary-container font-bold flex items-center gap-2">' +
      '<span class="material-symbols-outlined text-primary-container">psychology</span>Reasons</h4>' +
      '<span class="text-label-mono font-label-mono text-xs px-2.5 py-1 rounded-full bg-surface-container-highest border border-surface-container-high text-on-surface-variant">Signal Breakdown</span></div>' +

      '<div class="bg-background/80 rounded-lg p-3 border border-surface-container-high text-label-mono font-label-mono text-xs grid grid-cols-2 sm:grid-cols-3 gap-2">' +
      gridItem('Pair', result.pair || '') +
      gridItem('Timeframe', result.tf_label || '') +
      '<div><span class="text-on-surface-variant">Signal:</span> <span class="font-bold" style="color:' + color + '">' + dir + ' (' + (isBuy ? 'UP' : 'DOWN') + ')</span></div>' +
      gridItem('Confidence', (result.confidence || '') + '%') +
      gridItem('Trade Time', (result.trade_time || '—') + ' PKT') +
      gridItem('Candle starts', fmtPkt(result.candle_start)) +
      gridItem('Martingale', result.martingale_recommendation || 'M0') +
      '</div>' +

      '<div class="text-label-mono font-label-mono text-xs text-on-surface-variant flex flex-wrap justify-between gap-1 px-1">' +
      '<span>Data captured: <strong class="text-white">' + fmtPkt(result.data_timestamp) + '</strong></span>' +
      '<span>Vote: <strong class="text-primary-container">' + buyCount + ' BUY / ' + sellCount + ' SELL</strong> · Math ' + (result.math_score != null ? result.math_score + '/10' : '—') + '</span></div>' +

      (result.note ? '<p class="text-xs text-on-surface bg-surface-container/50 p-2.5 rounded-md border-l-2 border-primary-container">' + esc(result.note) + '</p>' : '') +

      votes.map(voteBlock).join('') +
      '</div>';

    startCountdown(result.timeframe_seconds || state.tf);
    startTradePoll(result);
  }

  function tradeBadge(res) {
    var r = res.trade_result || '';
    if (r === 'WIN')
      return '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30"><span class="material-symbols-outlined text-[14px]">check_circle</span>WIN</span>';
    if (r === 'LOSS')
      return '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold text-red-400 bg-red-500/10 border border-red-500/30"><span class="material-symbols-outlined text-[14px]">cancel</span>LOSS</span>';
    return '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold text-on-surface-variant bg-surface-container-high border border-surface-container-highest">' +
      '<span class="spinner" style="width:10px;height:10px"></span>Checking result…</span>';
  }

  /* Poll the trade result until the candle that opened at trade_time closes and
   * the backend marks the signal WIN / LOSS — same as the Telegram bot's wait. */
  function startTradePoll(result) {
    clearTradePoll();
    var jobId = result.job_id;
    var tf = result.timeframe_seconds || state.tf;
    var checkAtMs = Date.now() + (result.countdown + tf) * 1000 + 3000;
    var el = function () { return document.getElementById('sig-trade-result'); };
    if (!el()) return;
    tradePollTimer = setInterval(function () {
      var slot = el();
      if (!slot || !jobId) { clearTradePoll(); return; }
      if (Date.now() < checkAtMs) {
        slot.innerHTML = tradeBadge({});
        return;
      }
      api('/signal/' + jobId).then(function (j) {
        var r = j.result || {};
        var badge = tradeBadge({ trade_result: r.trade_result || '' });
        var slotEl = el();
        if (slotEl) slotEl.innerHTML = badge;
        if (r.trade_result === 'WIN' || r.trade_result === 'LOSS') clearTradePoll();
      }).catch(function () {});
    }, 4000);
  }

  function clearTradePoll() {
    if (tradePollTimer) { clearInterval(tradePollTimer); tradePollTimer = null; }
  }

  function gridItem(k, v) {
    return '<div><span class="text-on-surface-variant">' + esc(k) + ':</span> <span class="text-white font-bold">' + esc(v != null ? v : '—') + '</span></div>';
  }

  function voteBlock(v) {
    var isBuy = v.sign === 'BUY';
    var isSell = v.sign === 'SELL';
    var dot = isBuy ? 'bg-emerald-500' : isSell ? 'bg-red-500' : 'bg-surface-container-highest';
    var pillCls = isBuy ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' :
      isSell ? 'text-red-400 bg-red-500/10 border-red-500/30' :
      'text-on-surface-variant bg-surface-container border-surface-container-high';
    var pillText = v.sign + (v.confidence ? ' (' + v.confidence + '%)' : '');
    var ca = v.chart_analysis || {};
    var chartLines = '';
    if (Object.keys(ca).length) {
      var rows = [
        ['Visual chart', ca.visual_trend],
        ['Levels seen', ca.key_levels_seen],
        ['Pattern at price', ca.pattern_at_price],
      ].filter(function (r) { return r[1]; });
      chartLines = rows.map(function (r) {
        var c = String(r[1]).toUpperCase();
        var col = c.indexOf('DOWN') !== -1 || c.indexOf('SELL') !== -1 ? '#f87171' : (c.indexOf('UP') !== -1 || c.indexOf('BUY') !== -1) ? '#34d399' : '#fff';
        return '<div>• ' + esc(r[0]) + ': <span style="color:' + col + ';font-weight:700">' + esc(r[1]) + '</span></div>';
      }).join('');
    }
    var chain = [];
    if (v.chain_of_thought && typeof v.chain_of_thought === 'object') {
      for (var k in v.chain_of_thought) if (v.chain_of_thought[k]) chain.push('• ' + v.chain_of_thought[k]);
    }
    var analysis = [];
    if (v.analysis && typeof v.analysis === 'object') {
      for (var a in v.analysis) if (v.analysis[a]) analysis.push('<div>• ' + esc(a) + ': <span class="text-white">' + esc(v.analysis[a]) + '</span></div>');
    }

    return '<div class="bg-surface-container/80 rounded-lg p-3 border border-surface-container-high flex flex-col gap-2">' +
      '<div class="flex items-center justify-between">' +
      '<span class="font-bold text-sm text-primary-container flex items-center gap-1.5"><span class="w-2 h-2 rounded-full ' + dot + '"></span>' + esc(shortName(v.model)) + '</span>' +
      '<span class="text-xs font-bold font-label-mono px-2 py-0.5 rounded border ' + pillCls + '">' + esc(pillText) + '</span></div>' +
      (v.reason ? '<p class="text-xs text-on-surface leading-relaxed">' + esc(v.reason) + '</p>' : '') +
      ((chartLines || chain.length || analysis.length) ?
        '<div class="bg-background/90 p-2.5 rounded border border-surface-container-high text-[11px] font-label-mono text-on-surface-variant flex flex-col gap-1">' +
        (chartLines ? '<span class="text-primary-container font-bold border-b border-surface-container-high/50 pb-1 mb-0.5">CHART SEEN BY ' + esc(shortName(v.model).toUpperCase()) + '</span>' + chartLines : '') +
        chain.map(function (l) { return '<div>' + l + '</div>'; }).join('') +
        analysis.join('') +
        '</div>' : '') +
      '</div>';
  }

  /* ── countdown ── */
  function remaining() {
    var now = Math.floor(Date.now() / 1000);
    return Math.max(0, state.tf - (now % state.tf));
  }

  function startCountdown(tf) {
    clearCountdown();
    var el = document.getElementById('sig-countdown');
    if (!el) return;
    countdownTimer = setInterval(function () {
      if (!document.getElementById('sig-countdown')) { clearCountdown(); return; }
      var now = Math.floor(Date.now() / 1000);
      var rem = Math.max(0, tf - (now % tf));
      el.textContent = 'Next candle closes in ' + rem + 's';
    }, 1000);
  }

  function clearCountdown() {
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
  }

  /* ── recent signals (signals page) ── */
  async function refreshRecent() {
    var section = document.getElementById('sig-recent');
    var list = document.getElementById('sig-recent-list');
    if (!section || !list) return;
    try {
      var signals = await api('/signals?limit=5');
      if (!signals.length) { section.classList.add('hidden'); return; }
      section.classList.remove('hidden');
      list.innerHTML = signals.map(ux.signalRow).join('');
    } catch (e) {}
  }

  /* ── helpers ── */
  function shortName(m) { return SHORT[m] || String(m || 'Model').split(' ')[0]; }
  function isCrypto(sym) {
    var p = String(sym || '').toUpperCase();
    return ['BTC', 'ETH', 'XRP', 'DOGE', 'SOL', 'LTC', 'BCH', 'LINK', 'ADA', 'TRX', 'DOT', 'XBT', 'MATIC', 'TON', 'AVAX', 'ZEC', 'DASH', 'LUN'].some(function (c) { return p.indexOf(c) !== -1; });
  }
  function fmtTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  /* Epoch seconds (ms or s) → PKT (UTC+5) HH:MM:SS — matches Telegram bot's clock */
  function fmtPkt(ts) {
    if (!ts) return '—';
    var ms = Number(ts) < 1e12 ? Number(ts) * 1000 : Number(ts);
    var d = new Date(ms + 5 * 3600 * 1000);
    return d.toISOString().slice(11, 19) + ' PKT';
  }
  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
})();