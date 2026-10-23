/* Shared front-end for Statistically Speaking: polling, the doors on the stage, the record, the chart,
   the belief bars and the room board. Plain JS, no dependencies, no inline scripts: pages hand their
   URLs over in data attributes. */
(function (global) {
  'use strict';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function svgEl(tag, attrs) {
    var e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }

  function pct(x, digits) {
    return x == null ? '—' : (x * 100).toFixed(digits || 0) + '%';
  }

  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  function fetchJSON(url, body) {
    var init = { cache: 'no-store' };
    if (body !== undefined) {
      init.method = 'POST';
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    return fetch(url, init).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; },
                           function () { return { ok: false, status: r.status, body: { error: 'Something went wrong.' } }; });
    });
  }

  /* Poll a state URL; the page re-renders from each answer. */
  function poll(url, render, ms) {
    var timer = null;
    function tick() {
      fetchJSON(url).then(function (res) { if (res.ok) render(res.body); }).catch(function () {});
    }
    tick();
    if (ms) timer = setInterval(tick, ms);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) tick(); });
    return { now: tick, stop: function () { if (timer) clearInterval(timer); timer = null; } };
  }

  /* ── The doors ─────────────────────────────────────────────────────────── */
  var GOAT = '🐐', BOAT = '🚤';

  /* The three doors are built once per container and updated in place, so the panels swing and the
     prizes pop instead of flashing. spec: { status, role, pick, opened, boat, final, won, selectable,
     onSelect, refuse, onRefuse, mine } where mine is the word for the contestant's door ("your" or a
     name). refuse(d) returns why a door may not be chosen; such a door shakes and onRefuse gets the reason. */
  function doors(container, spec) {
    if (!container._doors) {
      container._doors = [1, 2, 3].map(function (d) {
        var b = el('button', 'door');
        b.type = 'button';
        var room = el('div', 'door-room');
        room.appendChild(el('span', 'door-prize'));
        var panel = el('div', 'door-panel');
        panel.appendChild(el('span', 'door-num', String(d)));
        panel.appendChild(el('i', 'door-knob'));
        b.appendChild(room);
        b.appendChild(panel);
        b.appendChild(el('span', 'door-tag'));
        b.addEventListener('click', function () {
          var s = container._spec;
          if (!s) return;
          if (s.selectable && s.selectable.indexOf(d) !== -1) { if (s.onSelect) s.onSelect(d); return; }
          var why = s.refuse ? s.refuse(d) : null;
          if (!why) return;
          b.classList.remove('nope');
          void b.offsetWidth;
          b.classList.add('nope');
          if (s.onRefuse) s.onRefuse(why);
        });
        b.addEventListener('animationend', function (e) { if (e.animationName === 'door-nope') b.classList.remove('nope'); });
        container.appendChild(b);
        return b;
      });
    }
    container._spec = spec;
    var revealed = spec.status === 'revealed';
    var selectable = spec.selectable || [];
    var mine = spec.mine || 'your';
    container._doors.forEach(function (b, i) {
      var d = i + 1;
      var isOpen = spec.opened === d || revealed;
      var boat = spec.boat === d;
      var prize = b.querySelector('.door-prize');
      var tag = '';
      b.classList.toggle('open', isOpen);
      b.classList.toggle('pick', spec.pick === d);
      b.classList.toggle('boat-known', !isOpen && boat);
      b.classList.toggle('won', revealed && spec.final === d && !!spec.won);
      b.classList.toggle('lost', revealed && spec.final === d && !spec.won);
      b.classList.toggle('selectable', selectable.indexOf(d) !== -1);
      if (isOpen) {
        prize.textContent = boat ? BOAT : GOAT;
        prize.className = 'door-prize ' + (boat ? 'boat' : 'goat');
        if (revealed && spec.final === d) tag = (spec.won ? '🏆 ' : '') + mine + ' door';
        else tag = boat ? 'the boat' : 'goat';
      } else {
        if (!boat) { prize.textContent = ''; prize.className = 'door-prize'; }
        if (spec.pick === d) tag = mine + ' pick';
        else if (boat) tag = 'boat · shh';
      }
      b.querySelector('.door-tag').textContent = tag;
      b.setAttribute('aria-label', 'Door ' + d + (tag ? ', ' + tag : ''));
      b.disabled = selectable.indexOf(d) === -1 && !(spec.refuse && spec.refuse(d));
      b.classList.toggle('refusable', !b.disabled && selectable.indexOf(d) === -1);
    });
  }

  /* A burst of confetti over a stage. Positions and colours go through the CSSOM, never inline markup. */
  function confetti(stage) {
    if (!stage || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var box = el('div', 'confetti');
    var colours = ['#f5c518', '#6c63ff', '#22c55e', '#ef4444', '#3b82f6', '#fff3b0'];
    for (var i = 0; i < 48; i++) {
      var bit = el('i');
      bit.style.left = (Math.random() * 100) + '%';
      bit.style.background = colours[i % colours.length];
      bit.style.animationDelay = (Math.random() * 0.8) + 's';
      bit.style.animationDuration = (2 + Math.random() * 1.2) + 's';
      box.appendChild(bit);
    }
    stage.appendChild(box);
    setTimeout(function () { if (box.parentNode) box.parentNode.removeChild(box); }, 4200);
  }

  /* ── The record ────────────────────────────────────────────────────────── */
  function arm(name, label, data, expected) {
    var a = el('div', 'arm ' + name);
    a.appendChild(el('h3', null, label));
    a.appendChild(el('div', 'big', pct(data.rate)));
    a.appendChild(el('div', 'frac', data.n ? data.wins + ' of ' + data.n + ' won' : 'no games yet'));
    var bar = el('div', 'bar'), fill = el('div', 'bar-fill'), mark = el('i', 'bar-mark');
    fill.style.width = pct(data.rate || 0);
    mark.style.left = pct(expected);
    mark.dataset.label = expected > 0.5 ? '2/3' : '1/3';
    mark.title = 'expected ' + pct(expected);
    bar.appendChild(fill); bar.appendChild(mark);
    a.appendChild(bar);
    return a;
  }

  function record(container, t) {
    container.innerHTML = '';
    var r = el('div', 'record');
    r.appendChild(arm('stay', 'Stay', t.stay, 1 / 3));
    r.appendChild(arm('switch', 'Switch', t.switch, 2 / 3));
    var foot = plural(t.games, 'game');
    if (t.games) foot += ' · the first pick was right ' + pct(t.first_pick_rate) + ' of the time (' + t.first_pick_right + ' of ' + t.games + ')';
    r.appendChild(el('p', 'record-foot', foot));
    container.appendChild(r);
  }

  /* ── The chart: both win rates after each revealed game ───────────────── */
  function chart(svg, series) {
    var W = 640, H = 280, L = 44, R = 40, T = 16, B = 36;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var n = series.length, maxX = Math.max(n, 10);
    var x = function (i) { return L + (i - 1) / (maxX - 1) * (W - L - R); };
    var y = function (v) { return T + (1 - v) * (H - T - B); };
    svg.appendChild(svgEl('line', { x1: L, y1: y(0), x2: W - R, y2: y(0), class: 'axis' }));
    svg.appendChild(svgEl('line', { x1: L, y1: y(1), x2: L, y2: y(0), class: 'axis' }));
    [[1 / 3, '1/3'], [1 / 2, '1/2'], [2 / 3, '2/3']].forEach(function (ref) {
      svg.appendChild(svgEl('line', { x1: L, y1: y(ref[0]), x2: W - R, y2: y(ref[0]), class: 'ref' }));
      var t = svgEl('text', { x: W - R + 6, y: y(ref[0]) + 4, class: 'label strong' });
      t.textContent = ref[1];
      svg.appendChild(t);
    });
    [0, 0.5, 1].forEach(function (v) {
      var t = svgEl('text', { x: L - 8, y: y(v) + 4, 'text-anchor': 'end', class: 'label' });
      t.textContent = Math.round(v * 100) + '%';
      svg.appendChild(t);
    });
    var xt = svgEl('text', { x: (L + W - R) / 2, y: H - 8, 'text-anchor': 'middle', class: 'label' });
    xt.textContent = 'games played';
    svg.appendChild(xt);
    if (!n) {
      var e = svgEl('text', { x: (L + W - R) / 2, y: (T + H - B) / 2, 'text-anchor': 'middle', class: 'empty' });
      e.textContent = 'The record starts with the first game.';
      svg.appendChild(e);
      return;
    }
    ['stay', 'switch'].forEach(function (name) {
      var d = '', last = null;
      series.forEach(function (p) {
        if (p[name] == null) return;
        d += (d ? ' L' : 'M') + x(p.game).toFixed(1) + ' ' + y(p[name]).toFixed(1);
        last = p;
      });
      if (!d) return;
      svg.appendChild(svgEl('path', { d: d, class: 'line ' + name }));
      svg.appendChild(svgEl('circle', { cx: x(last.game), cy: y(last[name]), r: 4, class: 'dot ' + name }));
      var lg = svgEl('text', { x: x(last.game) + 8, y: y(last[name]) - 7, class: 'legend ' + name });
      lg.textContent = name + ' ' + pct(last[name]);
      svg.appendChild(lg);
    });
  }

  /* ── Beliefs: before and after, as segmented bars ──────────────────────── */
  var CHOICES = [['switch', 'Switch'], ['stay', 'Stay'], ['same', 'No difference']];

  function beliefs(container, votes) {
    container.innerHTML = '';
    var box = el('div', 'beliefs');
    ['before', 'after'].forEach(function (phase) {
      var v = votes[phase], row = el('div', 'belief-row');
      row.appendChild(el('span', null, phase === 'before' ? 'Before' : 'After'));
      var bar = el('div', 'belief-bar');
      if (v.total) {
        CHOICES.forEach(function (c) {
          if (!v[c[0]]) return;
          var seg = el('span', 'belief-seg ' + c[0], v[c[0]]);
          seg.style.width = pct(v[c[0]] / v.total, 1);
          seg.title = c[1] + ': ' + v[c[0]] + ' of ' + v.total;
          bar.appendChild(seg);
        });
      } else {
        bar.appendChild(el('span', 'belief-seg', ''));
      }
      row.appendChild(bar);
      box.appendChild(row);
    });
    var legend = el('div', 'belief-legend');
    CHOICES.forEach(function (c) {
      var item = el('span');
      item.appendChild(el('i', c[0]));
      item.appendChild(document.createTextNode(c[1]));
      legend.appendChild(item);
    });
    box.appendChild(legend);
    container.appendChild(box);
  }

  /* ── The room: tables as they stand, and who is still looking ──────────── */
  function tableStatus(t, status) {
    if (t.members.length < 2) return 'waiting for a partner';
    if (status === 'lobby') return 'ready · waiting for the show to start';
    if (t.game && t.game.playing) return 'game ' + t.game.index + ' · ' + t.game.host + ' hosts';
    if (t.game) return plural(t.played, 'game') + ' played';
    return 'ready';
  }

  function room(container, room, status, me) {
    container.innerHTML = '';
    room.tables.forEach(function (t) {
      var box = el('div', 'tbl' + (t.game && t.game.playing ? ' playing' : ''));
      var head = el('div', 'tbl-head');
      head.appendChild(el('span', null, 'Table ' + t.index));
      head.appendChild(el('span', null, t.members.length + '/' + t.size));
      box.appendChild(head);
      var chips = el('div', 'chips');
      t.members.forEach(function (m) {
        var cls = 'chip';
        if (t.game && t.game.playing) {
          if (m.name === t.game.host) cls += ' host';
          else if (m.name === t.game.contestant) cls += ' contestant';
        }
        if (me && m.id === me) cls += ' me';
        var prefix = cls.indexOf(' host') !== -1 ? '🎤 ' : cls.indexOf(' contestant') !== -1 ? '🎯 ' : '';
        chips.appendChild(el('span', cls, prefix + m.name));
      });
      box.appendChild(chips);
      box.appendChild(el('div', 'tbl-status', tableStatus(t, status)));
      container.appendChild(box);
    });
    if (room.looking.length) {
      var box = el('div', 'tbl looking');
      box.appendChild(el('div', 'tbl-head', 'Still looking'));
      var chips = el('div', 'chips');
      room.looking.forEach(function (p) { chips.appendChild(el('span', 'chip' + (me && p.id === me ? ' me' : ''), p.name)); });
      box.appendChild(chips);
      container.appendChild(box);
    }
  }

  /* ── The plain-English numbers (mirrors logic.py for the solo page) ────── */
  function surprise(wins, n) {
    if (!n) return null;
    // Upper binomial tail at p = 1/2, summed in log space so large records stay finite.
    var total = 0;
    for (var k = wins; k <= n; k++) {
      var lc = 0;
      for (var i = 1; i <= k; i++) lc += Math.log(n - k + i) - Math.log(i);
      total += Math.exp(lc - n * Math.LN2);
    }
    return Math.min(total, 1);
  }

  function describe(decision, wins, n) {
    var p = surprise(wins, n);
    if (p == null) return 'Nobody has ' + (decision === 'switch' ? 'switched' : 'stayed') + ' yet.';
    var verb = decision === 'switch' ? 'switching' : 'staying';
    var head = 'If ' + verb + ' made no difference, winning at least ' + wins + ' of ' + n + ' would happen';
    if (p >= 0.5) return head + ' more than half the time.';
    if (p >= 0.2) return head + ' about ' + Math.round(p * 100) + '% of the time.';
    var oneIn = p > 0 ? Math.round(1 / p) : null;
    if (oneIn == null || oneIn > 1000000) return head + ' less than once in a million tries.';
    var pc = p >= 0.01 ? (p * 100).toFixed(1) : (p * 100).toFixed(2);
    return head + ' about ' + pc + '% of the time, roughly 1 in ' + oneIn.toLocaleString() + '.';
  }

  /* Forms that ask before they act carry their question in data-confirm. */
  function confirmForms() {
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (e) { if (!confirm(form.dataset.confirm)) e.preventDefault(); });
    });
  }

  /* Any button with data-dialog="id" opens that <dialog>; data-dialog-close inside closes it; so does the backdrop. */
  function dialogs() {
    document.querySelectorAll('button[data-dialog]').forEach(function (open) {
      var dialog = document.getElementById(open.dataset.dialog);
      if (!dialog || !dialog.showModal) return;
      open.addEventListener('click', function () { dialog.showModal(); });
      dialog.querySelectorAll('[data-dialog-close]').forEach(function (b) { b.addEventListener('click', function () { dialog.close(); }); });
      dialog.addEventListener('click', function (e) { if (e.target === dialog) dialog.close(); });
    });
  }

  global.Show = { el: el, pct: pct, plural: plural, fetchJSON: fetchJSON, poll: poll, doors: doors, confetti: confetti,
                  record: record, chart: chart, beliefs: beliefs, room: room, surprise: surprise, describe: describe,
                  confirmForms: confirmForms, dialogs: dialogs, GOAT: GOAT, BOAT: BOAT };
  confirmForms();
  dialogs();
})(window);
