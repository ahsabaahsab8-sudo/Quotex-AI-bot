/* ── Quotex AI — SPA shell: view switching + shared auth ───────────── */
(function () {
  'use strict';

  var views = {};
  var current = null;

  window.App = {
    user: null,
    ensureAuth: async function () {
      if (App.user) return App.user;
      try {
        App.user = await api('/me');
      } catch (e) {
        // local auto sign-in (demo) so the app just works
        try {
          await api('/auth/demo', { method: 'POST', body: {} });
          App.user = await api('/me');
        } catch (e2) {
          throw e2;
        }
      }
      return App.user;
    },
    register: function (name, hooks) { views[name] = hooks; },
    current: function () { return current; },
    show: function (name) {
      if (!views[name]) {
        toast('“' + name + '” menu — building in the next step', 'info');
        return;
      }
      current = name;
      document.querySelectorAll('[id^="page-"]').forEach(function (p) {
        p.classList.toggle('hidden', p.id !== 'page-' + name);
      });
      document.querySelectorAll('.nav-tab').forEach(function (b) {
        var on = b.dataset.route === name;
        b.classList.toggle('text-primary-container', on);
        b.classList.toggle('text-on-surface-variant', !on);
        b.classList.toggle('font-bold', on);
        var ic = b.querySelector('.nav-ico');
        if (ic) ic.style.fontVariationSettings = "'FILL' " + (on ? 1 : 0) + ", 'wght' 400";
      });
      if (views[name].run) views[name].run();
    },
  };

  document.addEventListener('DOMContentLoaded', async function () {
    document.querySelectorAll('.nav-tab').forEach(function (b) {
      b.addEventListener('click', function () {
        App.show(b.dataset.route);
      });
    });
    try {
      await App.ensureAuth();
    } catch (e) {
      toast('Auth failed: ' + e.message, 'error');
    }
    App.show('home');
  });
})();