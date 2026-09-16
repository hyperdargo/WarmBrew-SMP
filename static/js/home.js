/* Home page motion. Every effect is a pure function of scroll position, so it scrubs
   backwards exactly as it plays forwards. One rAF loop, transform/opacity/canvas only.
   prefers-reduced-motion: the hero stays a still image, strikes and console show their final state. */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var vh = window.innerHeight;
  var updaters = [];
  var resizers = [];
  var queued = false;

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function range(p, start, end) { return clamp((p - start) / (end - start), 0, 1); }

  function frame() {
    queued = false;
    for (var i = 0; i < updaters.length; i++) updaters[i]();
  }
  function request() {
    if (!queued) { queued = true; requestAnimationFrame(frame); }
  }

  window.addEventListener('scroll', request, { passive: true });
  window.addEventListener('resize', function () {
    vh = window.innerHeight;
    for (var i = 0; i < resizers.length; i++) resizers[i]();
    request();
  }, { passive: true });

  // ------------------------------------------------------------------ signature: the cup comes apart

  function initHero() {
    var hero = document.querySelector('[data-hero]');
    if (!hero || reduced) return;
    var canvas = hero.querySelector('[data-cup]');
    var ctx = canvas && canvas.getContext('2d');
    if (!ctx) return;

    var night = hero.querySelector('[data-hero-night]');
    var calm = hero.querySelector('[data-line-calm]');
    var wild = hero.querySelector('[data-line-wild]');
    var hint = hero.querySelector('[data-hero-hint]');
    var copy = hero.querySelector('.hero__copy');

    var GRID = 32;
    var particles = [];
    var width = 0, height = 0, dpr = 1;
    var cell = 0, originX = 0, originY = 0, reach = 0;
    var lastP = -1;

    // Deterministic randomness so the explosion is identical every time you scrub through it.
    function mulberry32(seed) {
      return function () {
        seed |= 0; seed = seed + 0x6D2B79F5 | 0;
        var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
        t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
        return ((t ^ t >>> 14) >>> 0) / 4294967296;
      };
    }

    function buildParticles(image) {
      var size = image.naturalWidth;
      var step = size / GRID;
      var sample = document.createElement('canvas');
      sample.width = size;
      sample.height = size;
      var sctx = sample.getContext('2d');
      sctx.drawImage(image, 0, 0);
      var data = sctx.getImageData(0, 0, size, size).data;
      var rand = mulberry32(2718);
      var blastX = 15.5, blastY = 19;

      for (var gy = 0; gy < GRID; gy++) {
        for (var gx = 0; gx < GRID; gx++) {
          var px = Math.floor(gx * step + step / 2);
          var py = Math.floor(gy * step + step / 2);
          var o = (py * size + px) * 4;
          if (data[o + 3] < 128) continue;

          var ddx = gx - blastX, ddy = gy - blastY;
          var len = Math.sqrt(ddx * ddx + ddy * ddy) || 1;
          var angle = Math.atan2(ddy, ddx) + (rand() - 0.5) * 0.9;
          var shell = clamp(len / 18, 0, 1);

          particles.push({
            gx: gx, gy: gy,
            r: data[o], g: data[o + 1], b: data[o + 2],
            color: 'rgb(' + data[o] + ',' + data[o + 1] + ',' + data[o + 2] + ')',
            dx: Math.cos(angle), dy: Math.sin(angle),
            dist: 0.35 + rand() * 0.85,
            lift: 0.15 + rand() * 0.45,
            spin: (rand() - 0.5) * 7,
            depth: 0.6 + rand() * 1.5,
            delay: (1 - shell) * 0.16 + rand() * 0.07,
            spark: rand() < 0.08,
            wobble: rand() * Math.PI * 2
          });
        }
      }
    }

    function layout() {
      var rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);

      var cupSize;
      if (width > 820) {
        cupSize = Math.min(width * 0.34, 480);
        originX = width - width * 0.06 - cupSize;
        originY = (height - cupSize) / 2;
      } else {
        var headerH = 64;
        var copyTop = copy.getBoundingClientRect().top - rect.top;
        var room = copyTop - headerH - 32;
        cupSize = Math.max(96, Math.min(width * 0.6, 288, room));
        originX = (width - cupSize) / 2;
        originY = headerH + Math.max(12, (room - cupSize) / 2 + 8);
      }
      cell = cupSize / GRID;
      reach = Math.max(width, height) * 0.62;
      lastP = -1;
    }

    function draw(p) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 0.06–0.16: the cup trembles. 0.14–0.80: it blows apart. After that the debris hangs.
      var tremble = range(p, 0.05, 0.15) * (1 - range(p, 0.15, 0.2));
      var burst = range(p, 0.14, 0.8);

      for (var i = 0; i < particles.length; i++) {
        var q = particles[i];
        var t = clamp((burst - q.delay) / 0.76, 0, 1);
        var e = 1 - Math.pow(1 - t, 3);

        var homeX = originX + (q.gx + 0.5) * cell;
        var homeY = originY + (q.gy + 0.5) * cell;
        var shake = tremble * cell * 0.22;

        var x = homeX + q.dx * q.dist * reach * e + Math.sin(p * 900 + q.wobble) * shake;
        var y = homeY + q.dy * q.dist * reach * e - q.lift * reach * e + t * t * reach * 0.45
          + Math.cos(p * 820 + q.wobble) * shake;
        var s = cell * (1 + (q.depth - 1) * e) * (t === 0 ? 1.03 : 1);
        var rot = q.spin * e;

        ctx.globalAlpha = t < 0.6 ? 1 : 1 - (t - 0.6) / 0.4 * 0.86;

        if (q.spark && t > 0 && t < 0.45) {
          var heat = Math.sin((t / 0.45) * Math.PI) * 0.8;
          ctx.fillStyle = 'rgb(' +
            Math.round(q.r + (255 - q.r) * heat) + ',' +
            Math.round(q.g + (170 - q.g) * heat) + ',' +
            Math.round(q.b + (0 - q.b) * heat) + ')';
        } else {
          ctx.fillStyle = q.color;
        }

        var cos = Math.cos(rot) * s * dpr;
        var sin = Math.sin(rot) * s * dpr;
        ctx.setTransform(cos, sin, -sin, cos, x * dpr, y * dpr);
        ctx.fillRect(-0.5, -0.5, 1, 1);
      }
      ctx.globalAlpha = 1;
    }

    function progress() {
      var r = hero.getBoundingClientRect();
      var travel = r.height - vh;
      return { p: travel > 0 ? clamp(-r.top / travel, 0, 1) : 0, visible: r.bottom > 0 };
    }

    function update() {
      var state = progress();
      if (!state.visible) return;
      var p = state.p;
      if (p === lastP) return;
      lastP = p;

      draw(p);

      var dark = range(p, 0.12, 0.55);
      var calmOut = range(p, 0.2, 0.34);
      var wildIn = range(p, 0.36, 0.52);
      night.style.opacity = dark;
      calm.style.opacity = 1 - calmOut;
      calm.style.transform = 'translate3d(0,' + (-24 * calmOut) + 'px,0)';
      wild.style.opacity = wildIn;
      wild.style.transform = 'translate3d(0,' + (24 * (1 - wildIn)) + 'px,0)';
      if (hint) hint.style.opacity = 1 - range(p, 0, 0.06);
    }

    var image = new Image();
    image.onload = function () {
      try {
        buildParticles(image);
      } catch (err) {
        return; // canvas unreadable: keep the static logo
      }
      hero.classList.add('is-cinematic');
      layout();
      updaters.push(update);
      resizers.push(layout);
      request();
    };
    image.src = canvas.getAttribute('data-src');
  }

  // ------------------------------------------------------------------ strike-throughs

  function initStrikes() {
    var rows = Array.prototype.slice.call(document.querySelectorAll('[data-strike]'));
    if (!rows.length || reduced) return;
    var section = rows[0].closest('section');
    var strikes = rows.map(function (row) { return row.querySelector('.strike'); });

    updaters.push(function () {
      var box = section.getBoundingClientRect();
      if (box.bottom < 0 || box.top > vh) return;
      for (var i = 0; i < rows.length; i++) {
        var top = rows[i].getBoundingClientRect().top;
        // Starts when the command crosses 85% of the viewport, finished by 55%.
        var p = clamp((vh * 0.85 - top) / (vh * 0.3), 0, 1);
        strikes[i].style.transform = 'scaleX(' + p + ')';
        rows[i].classList.toggle('is-struck', p >= 1);
      }
    });
    request();
  }

  // ------------------------------------------------------------------ join console

  function initConsole() {
    var section = document.querySelector('[data-join]');
    if (!section) return;
    var panel = section.querySelector('.join__console');
    var lines = Array.prototype.slice.call(section.querySelectorAll('[data-console-line]'));
    var radios = section.querySelectorAll('[data-account]');

    function account() {
      var checked = section.querySelector('[data-account]:checked');
      return checked ? checked.value : 'premium';
    }
    function textFor(line) {
      return line.getAttribute('data-text') || line.getAttribute('data-text-' + account()) || '';
    }

    if (reduced) {
      var fill = function () { lines.forEach(function (l) { l.textContent = textFor(l); }); };
      fill();
      Array.prototype.forEach.call(radios, function (r) { r.addEventListener('change', fill); });
      return;
    }

    Array.prototype.forEach.call(radios, function (r) {
      r.addEventListener('change', function () { request(); });
    });

    updaters.push(function () {
      if (panel.offsetParent === null) return; // console hidden on small screens
      var box = section.getBoundingClientRect();
      if (box.bottom < 0 || box.top > vh) return;

      var steps = Array.prototype.filter.call(section.querySelectorAll('.step'), function (s) {
        return s.offsetParent !== null;
      });
      var active = -1;

      steps.forEach(function (step, i) {
        var top = step.getBoundingClientRect().top;
        var p = clamp((vh * 0.72 - top) / (vh * 0.28), 0, 1);
        var text = lines[i] ? textFor(lines[i]) : '';
        if (lines[i]) {
          lines[i].textContent = text.slice(0, Math.round(text.length * p));
          lines[i].classList.remove('is-typing');
        }
        if (p > 0) active = i;
        step.classList.remove('is-active');
      });

      if (active >= 0) {
        steps[active].classList.add('is-active');
        if (lines[active]) lines[active].classList.add('is-typing');
      }
    });
    request();
  }

  // ------------------------------------------------------------------ live status

  function initStatus() {
    var root = document.querySelector('[data-status]');
    if (!root) return;
    var dot = root.querySelector('[data-status-dot]');
    var state = root.querySelector('[data-status-state]');
    var players = root.querySelector('[data-status-players]');
    var version = root.querySelector('[data-status-version]');
    var motd = root.querySelector('[data-status-motd]');

    function render(data) {
      dot.classList.remove('is-online', 'is-offline');
      if (data && data.online) {
        dot.classList.add('is-online');
        state.textContent = 'Online';
        players.textContent = data.players + ' / ' + data.max;
        version.textContent = data.version || '–';
        motd.textContent = data.motd || '–';
      } else if (data) {
        dot.classList.add('is-offline');
        state.textContent = 'Offline';
        players.textContent = '–';
        version.textContent = '–';
        motd.textContent = 'The server isn’t answering right now. Check back in a few minutes.';
      } else {
        state.textContent = 'Unknown';
        players.textContent = '–';
        version.textContent = '–';
        motd.textContent = 'Couldn’t check the server just now. It may still be up, try joining.';
      }
    }

    function load() {
      fetch('/api/status', { headers: { Accept: 'application/json' } })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(render)
        .catch(function () { render(null); });
    }

    load();
    setInterval(function () { if (!document.hidden) load(); }, 60000);
  }

  initHero();
  initStrikes();
  initConsole();
  initStatus();
})();
