/* Full Monty on a phone: the two questions, and one game at a time at your table. */
(function () {
  'use strict';
  var root = document.getElementById('student');
  var STATE = root.dataset.stateUrl, ACT = root.dataset.actUrl, VOTE = root.dataset.voteUrl;
  var el = Show.el, phase = null, latest = null, busy = false, playKey = null, voteKeys = {};
  var CHOICES = [['switch', 'Switch'], ['stay', 'Stay'], ['same', 'No difference']];
  var poller;

  function show(id) {
    if (phase === id) return;
    phase = id;
    document.querySelectorAll('.phase').forEach(function (p) { p.hidden = p.id !== id; });
    window.scrollTo(0, 0);
  }

  function error(message) {
    var e = document.getElementById('error');
    e.hidden = !message;
    e.textContent = message || '';
  }

  function act(action, extra) {
    if (busy) return;
    busy = true;
    error('');
    Show.fetchJSON(ACT, Object.assign({ action: action }, extra || {})).then(function (res) {
      busy = false;
      if (res.ok) render(res.body); else { error(res.body.error); poller.now(); }
    }).catch(function () { busy = false; });
  }

  /* ── The two questions ────────────────────────────────────────────────── */
  function voteBlock(container, which, current, question) {
    var key = which + ':' + (current || '');
    if (voteKeys[which] === key) return;
    voteKeys[which] = key;
    container.innerHTML = '';
    container.appendChild(el('p', 'question', question));
    var box = el('div', 'vote');
    CHOICES.forEach(function (c) {
      var b = el('button', 'btn btn-large', c[1]);
      b.type = 'button';
      b.setAttribute('aria-pressed', current === c[0] ? 'true' : 'false');
      b.addEventListener('click', function () {
        Show.fetchJSON(VOTE, { phase: which, choice: c[0] }).then(function (res) {
          if (!res.ok) error(res.body.error);
          poller.now();
        });
      });
      box.appendChild(b);
    });
    container.appendChild(box);
    if (current) container.appendChild(el('p', 'muted small', 'Answer saved. You can change it until the show moves on.'));
  }

  /* ── Play ─────────────────────────────────────────────────────────────── */
  function other(pick, opened) { return [1, 2, 3].filter(function (d) { return d !== pick && d !== opened; })[0]; }

  function renderPlay(s) {
    show('phase-play');
    var g = s.game, t = s.table;
    var key = JSON.stringify([g, t, s.session.rule]);
    if (key === playKey) return;
    playKey = key;
    document.getElementById('table-line').textContent = 'Table ' + t.index + ' · with ' + t.partner + ' · game ' + g.index;
    document.getElementById('table-record').textContent = t.played ? 'At this table: ' + t.played + ' game' + (t.played === 1 ? '' : 's') + ' played' : '';
    var prompt = document.getElementById('prompt'), panel = document.getElementById('panel'), doors = document.getElementById('doors');
    panel.innerHTML = '';
    var host = g.role === 'host', who = host ? g.contestant : g.host;
    var spec = { status: g.status, role: g.role, pick: g.pick, opened: g.opened, car: g.car, final: g.final, won: g.won };
    var text = '';

    if (g.status === 'hiding') {
      if (host) { text = 'Hide the car. Tap a door.'; spec.selectable = [1, 2, 3]; spec.onSelect = function (d) { act('hide', { door: d }); }; }
      else text = who + ' is hiding the car.';
    } else if (g.status === 'picking') {
      if (host) text = 'The car is behind door ' + g.car + '. ' + who + ' is picking.';
      else { text = 'Pick a door.'; spec.selectable = [1, 2, 3]; spec.onSelect = function (d) { act('pick', { door: d }); }; }
    } else if (g.status === 'opening') {
      if (host) { text = who + ' picked door ' + g.pick + '. Open a door that hides a goat.'; spec.selectable = g.legal || []; spec.onSelect = function (d) { act('open', { door: d }); }; }
      else text = 'You picked door ' + g.pick + '. ' + who + ' is opening a door.';
    } else if (g.status === 'deciding') {
      var alt = other(g.pick, g.opened), rule = s.session.rule;
      if (host) text = 'Door ' + g.opened + ' is open. Ask ' + who + ': stay with door ' + g.pick + ', or switch to door ' + alt + '?';
      else {
        text = 'Door ' + g.opened + ' is open: a goat. Stay with door ' + g.pick + ', or switch to door ' + alt + '?';
        var choice = el('div', 'choice');
        [['stay', 'Stay with ' + g.pick], ['switch', 'Switch to ' + alt]].forEach(function (c) {
          var b = el('button', 'btn btn-' + c[0], c[1]);
          b.type = 'button';
          if (rule !== 'choice' && rule !== c[0]) b.disabled = true;
          b.addEventListener('click', function () { act('decide', { decision: c[0] }); });
          choice.appendChild(b);
        });
        panel.appendChild(choice);
        if (rule !== 'choice') panel.appendChild(el('p', 'muted small', 'Rule right now: everyone ' + (rule === 'stay' ? 'stays' : 'switches') + '.'));
      }
    } else if (g.status === 'revealed') {
      var moved = g.decision === 'switch' ? 'switched to' : 'stayed with';
      text = host ? who + ' ' + moved + ' door ' + g.final + '.' : 'You ' + moved + ' door ' + g.final + '.';
      panel.appendChild(el('div', 'result ' + (g.won ? 'won' : 'lost'), g.won ? (host ? 'The car. ' + who + ' wins.' : 'The car. You win.') : (host ? 'A goat.' : 'A goat.')));
      var next = el('button', 'btn btn-primary btn-large btn-block', 'Next game');
      next.type = 'button';
      next.addEventListener('click', function () { act('next', { game: g.id }); });
      panel.appendChild(next);
      if (!t.house) panel.appendChild(el('p', 'muted small', 'Partners swap roles next game.'));
    } else {
      text = 'This game was dropped.';
    }
    prompt.textContent = text;
    Show.doors(doors, spec);
  }

  /* ── The end ──────────────────────────────────────────────────────────── */
  function renderEnded(s) {
    show('phase-ended');
    var votes = s.you.votes || {};
    voteBlock(document.getElementById('after-vote'), 'after', votes.after,
              'Now that you have seen the record: the host opens a goat door and offers the switch. Which is the better move?');
    var box = document.getElementById('summary'), y = s.summary;
    if (!y || box.dataset.done) return;
    box.dataset.done = '1';
    box.innerHTML = '';
    var p = el('p');
    if (y.played) {
      var arms = [];
      if (y.stay.n) arms.push('Staying won ' + y.stay.wins + ' of ' + y.stay.n);
      if (y.switch.n) arms.push('switching won ' + y.switch.wins + ' of ' + y.switch.n);
      p.textContent = 'You played ' + y.played + ' game' + (y.played === 1 ? '' : 's') + ' as contestant' +
        (y.hosted ? ' and hosted ' + y.hosted : '') + '. ' + arms.join('; ') + '. Your first pick was right ' +
        y.first_pick_right + ' of ' + y.played + ' time' + (y.played === 1 ? '' : 's') + '.';
    } else {
      p.textContent = y.hosted ? 'You hosted ' + y.hosted + ' game' + (y.hosted === 1 ? '' : 's') + '.' : 'You did not get to play this time.';
    }
    box.appendChild(p);
    if (y.games.length) {
      var ul = el('ul', 'games-list');
      y.games.forEach(function (g) {
        ul.appendChild(el('li', null, 'Table ' + g.table + ', game ' + g.index + ': picked ' + g.pick + ', ' +
          (g.decision === 'switch' ? 'switched to ' : 'stayed with ') + g.final + ', car behind ' + g.car + '. ' + (g.won ? 'Won.' : 'Goat.')));
      });
      box.appendChild(ul);
    }
    var rec = el('div', 'summary-record');
    rec.appendChild(el('h2', null, 'The class record'));
    var r = el('div');
    rec.appendChild(r);
    Show.record(r, s.record.tallies);
    if (s.record.tallies.switch.n) rec.appendChild(el('p', 'small', s.record.text.switch));
    box.appendChild(rec);
  }

  function render(s) {
    latest = s;
    if (s.session.status === 'ended') return renderEnded(s);
    if (!s.table || !s.game) {
      show('phase-lobby');
      voteBlock(document.getElementById('before-vote'), 'before', (s.you.votes || {}).before,
                'Before you play: the host opens a goat door and offers the switch. Which is the better move?');
      document.getElementById('lobby-note').textContent = s.session.status === 'active' ? 'Waiting for your teacher to seat you.' : 'Waiting for your teacher to seat everyone.';
      return;
    }
    renderPlay(s);
  }

  poller = Show.poll(STATE, render, 1500);
})();
