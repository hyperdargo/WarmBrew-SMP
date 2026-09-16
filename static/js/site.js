/* Shared behaviour for every page: copy-IP buttons, toast, header state, form double-submit guard. */
(function () {
  'use strict';

  var toastEl = document.querySelector('[data-toast]');
  var toastTimer;

  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('is-visible'); }, 2200);
  }

  // navigator.clipboard only exists on HTTPS/localhost; the site may be served over plain HTTP.
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      area.remove();
      ok ? resolve() : reject(new Error('copy failed'));
    });
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-copy]');
    if (!button) return;
    var text = button.getAttribute('data-copy');
    var label = button.querySelector('[data-copy-label]');

    copyText(text).then(function () {
      button.classList.add('is-copied');
      if (label) label.textContent = 'Copied';
      toast('IP copied. See you in-game.');
      setTimeout(function () {
        button.classList.remove('is-copied');
        if (label) label.textContent = 'Copy IP';
      }, 1800);
    }).catch(function () {
      var ip = button.querySelector('.ip-button__ip');
      if (ip) window.getSelection().selectAllChildren(ip);
      toast('Press Ctrl+C to copy the selected IP.');
    });
  });

  // Home page header starts transparent over the hero and turns solid once you scroll.
  var header = document.querySelector('.site-header');
  if (header && document.body.classList.contains('page-home')) {
    var queued = false;
    var sync = function () {
      queued = false;
      header.classList.toggle('is-solid', window.scrollY > 24);
    };
    window.addEventListener('scroll', function () {
      if (!queued) { queued = true; requestAnimationFrame(sync); }
    }, { passive: true });
    sync();
  }

  document.addEventListener('submit', function (event) {
    var form = event.target;
    var button = form.querySelector('[data-submit]');
    if (form.dataset.sending) { event.preventDefault(); return; }
    form.dataset.sending = '1';
    if (button) {
      button.dataset.label = button.textContent;
      button.disabled = true;
      button.textContent = 'Sending…';
    }
  });

  // Restore buttons if the page comes back from the back/forward cache.
  window.addEventListener('pageshow', function (event) {
    if (!event.persisted) return;
    document.querySelectorAll('form[data-sending]').forEach(function (form) {
      delete form.dataset.sending;
      var button = form.querySelector('[data-submit]');
      if (button) {
        button.disabled = false;
        if (button.dataset.label) button.textContent = button.dataset.label;
      }
    });
  });
})();
