/* ── Quotex AI Live — embeds the real QuotexChart desktop app 1:1 ────
 * The Live menu shows the SAME EEL chart app that runs as a window:
 * it is served headless on http://localhost:8010 (live_server.py) and
 * embedded here via <iframe>, so assets / timeframes / indicators /
 * editor / live candles all behave exactly like the desktop app.
 */
(function () {
  'use strict';

  App.register('live', { run: run });

  function run() {
    bindReload();
  }

  function bindReload() {
    var btn = document.getElementById('live-reload');
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', function () {
      var f = document.getElementById('live-iframe');
      if (f) {
        f.src = f.src;
        toast('Reloading live chart…', 'info');
      }
    });
  }
})();