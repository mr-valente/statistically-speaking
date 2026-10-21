/* Shared front-end for Statistically Speaking: polling, the doors, the record, the chart and the
   belief bars. Plain JS, no dependencies, no inline scripts: pages hand their URLs over in data attributes. */
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

  /* ── Doors ─────────────────────────────────────────────────────────────── */
  var GOAT = '🐐', CAR = '🚗';

  /* spec: { status, role, pick, opened, car, final, won, legal, selectable: [doors], onSelect } */
  function doors(container, spec) {
    container.innerHTML = '';
    var revealed = spec.status === 'revealed';
    var selectable = spec.selectable || [];
    var mine = spec.role === 'contestant' ? 'your' : 'their';
    [1, 2, 3].forEach(function (d) {
      var isOpen = spec.opened === d || revealed;
      var b = el('button', 'door');
      b.type = 'button';
      var tag = '';
      if (isOpen) {
        b.classList.add('open');
        var car = spec.car === d;
        b.appendChild(el('span', 'glyph', car ? CAR : GOAT));
        tag = car ? 'car' : 'goat';
        if (revealed && spec.final === d) {
          b.classList.add(spec.won ? 'won' : 'lost');
          tag = mine + ' door · ' + tag;
        }
      } else {
        b.appendChild(el('span', 'num', String(d)));
        if (spec.pick === d) { b.classList.add('pick'); tag = mine + ' pick'; }
        else if (spec.car === d) { b.classList.add('car-known'); tag = 'car'; }
      }
      b.appendChild(el('span', 'tag', tag));
      b.setAttribute('aria-label', 'Door ' + d + (tag ? ', ' + tag : ''));
      if (selectable.indexOf(d) !== -1) {
        b.classList.add('selectable');
        b.addEventListener('click', function () { spec.onSelect(d); });
      } else {
        b.disabled = true;
      }
      container.appendChild(b);
    });
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
    var foot = t.games + ' game' + (t.games === 1 ? '' : 's');
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

  /* Forms that ask before they act carry their question in data-confirm. */
  function confirmForms() {
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (e) { if (!confirm(form.dataset.confirm)) e.preventDefault(); });
    });
  }

  function qrDialog() {
    var open = document.getElementById('qr-open'), dialog = document.getElementById('qr-dialog');
    if (!open || !dialog || !dialog.showModal) return;
    open.addEventListener('click', function () { dialog.showModal(); });
    document.getElementById('qr-close').addEventListener('click', function () { dialog.close(); });
    dialog.addEventListener('click', function (e) { if (e.target === dialog) dialog.close(); });
  }

  global.Show = { el: el, pct: pct, fetchJSON: fetchJSON, poll: poll, doors: doors, record: record,
                  chart: chart, beliefs: beliefs, confirmForms: confirmForms, qrDialog: qrDialog };
})(window);
