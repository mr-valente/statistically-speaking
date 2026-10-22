/* Full Monty on a phone: the two questions, finding a table, and one game at a time. */
(function () {
  'use strict';
  var root = document.getElementById('student');
  var STATE = root.dataset.stateUrl, ACT = root.dataset.actUrl, SEAT = root.dataset.seatUrl, VOTE = root.dataset.voteUrl, ME = root.dataset.me;
  var el = Show.el, phase = null, busy = false, playKey = null, lobbyKey = null, inboxKey = null, voteKeys = {}, celebrated = null;
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

  function send(url, body) {
    if (busy) return;
    busy = true;
    error('');
    Show.fetchJSON(url, body).then(function (res) {
      busy = false;
      if (res.ok) render(res.body); else { error(res.body.error); flash(res.body.error); poller.now(); }
    }).catch(function () { busy = false; });
  }

  function act(action, extra) { send(ACT, Object.assign({ action: action }, extra || {})); }
  function seating(action, extra) { send(SEAT, Object.assign({ action: action }, extra || {})); }

  /* A refusal while finding a table shows up at the top, where the lobby can see it. */
  function flash(message) {
    var box = document.getElementById('inbox');
    var old = box.querySelector('.ask.flash');
    if (old) old.remove();
    if (!message || phase !== 'phase-lobby') return;
    var note = el('div', 'ask flash');
    note.appendChild(el('span', null, message));
    box.appendChild(note);
    setTimeout(function () { if (note.parentNode) note.remove(); }, 3500);
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
      var b = el('button', 'vote-btn', c[1]);
      b.type = 'button';
      b.setAttribute('aria-pressed', current === c[0] ? 'true' : 'false');
      b.addEventListener('click', function () {
        Show.fetchJSON(VOTE, { phase: which, choice: c[0] }).then(function (res) {
          if (!res.ok) flash(res.body.error);
          poller.now();
        });
      });
      box.appendChild(b);
    });
    container.appendChild(box);
    if (current) container.appendChild(el('p', 'sub small', 'Answer saved. You can change your mind until the show moves on.'));
  }

  /* ── Requests to sit together, visible in any phase ───────────────────── */
  function renderInbox(s) {
    var inbox = s.you.inbox || [];
    var key = JSON.stringify(inbox);
    if (key === inboxKey) return;
    inboxKey = key;
    var box = document.getElementById('inbox');
    box.innerHTML = '';
    inbox.forEach(function (r) {
      var ask = el('div', 'ask');
      var text = el('span');
      var who = el('strong', null, r.from);
      text.appendChild(who);
      text.appendChild(document.createTextNode(s.table ? ' wants to join your table.' : ' wants to sit with you.'));
      ask.appendChild(text);
      var yes = el('button', 'btn btn-sm btn-success', 'Sure!');
      yes.type = 'button';
      yes.addEventListener('click', function () { seating('accept', { request: r.id }); });
      var no = el('button', 'btn btn-sm btn-ghost', 'Not now');
      no.type = 'button';
      no.addEventListener('click', function () { seating('decline', { request: r.id }); });
      ask.appendChild(yes);
      ask.appendChild(no);
      box.appendChild(ask);
    });
  }

  /* ── Finding a table ──────────────────────────────────────────────────── */
  function nameButton(p, action) {
    var b = el('button', 'name-btn', p.name);
    b.type = 'button';
    b.addEventListener('click', action);
    return b;
  }

  function renderLobby(s) {
    show('phase-lobby');
    var votes = s.you.votes || {};
    var before = document.getElementById('before-vote');
    if (!(s.table && s.table.played)) {
      voteBlock(before, 'before', votes.before,
                'Before you play: the host opens a goat door and offers you the switch. What\'s the better move?');
    } else {
      before.innerHTML = '';
      voteKeys.before = null;
    }
    var key = JSON.stringify([s.room, s.you.asked, s.table, s.session.status]);
    if (key === lobbyKey) return;
    lobbyKey = key;

    var seated = !!s.table, active = s.session.status === 'active';
    var title = document.getElementById('lobby-title'), note = document.getElementById('lobby-note');
    var mine = document.getElementById('my-table'), asked = document.getElementById('asked');
    var looking = document.getElementById('looking'), tables = document.getElementById('tables');
    mine.innerHTML = ''; asked.innerHTML = ''; looking.innerHTML = ''; tables.innerHTML = '';

    if (seated) {
      title.textContent = 'Table ' + s.table.index;
      note.textContent = '';
      var box = el('div', 'my-table');
      var names = el('div', 'names');
      s.table.members.forEach(function (n) { names.appendChild(el('span', 'chip' + (n === s.you.name ? ' me' : ''), n)); });
      box.appendChild(names);
      if (s.table.members.length < 2) {
        box.appendChild(el('p', 'sub pulse', 'Your partner left. Tap someone who\'s still looking to invite them.'));
      } else if (!active) {
        box.appendChild(el('p', 'sub pulse', '🍿 Your table is set. Waiting for the show to start…'));
        if (s.table.room) box.appendChild(el('p', 'sub small', 'Room for one more. Tap someone who\'s still looking to invite them.'));
      }
      var leave = el('button', 'btn btn-ghost btn-sm', 'Leave this table');
      leave.type = 'button';
      leave.addEventListener('click', function () { seating('leave'); });
      var p = el('p');
      p.appendChild(leave);
      box.appendChild(p);
      mine.appendChild(box);
    } else {
      title.textContent = 'Find a table';
      note.textContent = 'Tap a classmate to ask to sit together. Tables seat two or three.';
    }

    if (s.you.asked) {
      var line = el('div', 'asked');
      line.appendChild(el('span', 'pulse', 'Asked ' + s.you.asked.to + '… waiting for a yes.'));
      var cancel = el('button', 'btn btn-ghost btn-sm', 'Take it back');
      cancel.type = 'button';
      cancel.addEventListener('click', function () { seating('cancel'); });
      line.appendChild(cancel);
      asked.appendChild(line);
    }

    var others = s.room.looking.filter(function (p) { return p.id !== ME; });
    var canAsk = !seated || s.table.room;
    looking.appendChild(el('h4', null, 'Still looking'));
    if (others.length) {
      var names2 = el('div', 'names');
      others.forEach(function (p) {
        var b = nameButton(p, function () { seating('ask', { player: p.id }); });
        if (!canAsk) b.disabled = true;
        names2.appendChild(b);
      });
      looking.appendChild(names2);
    } else {
      looking.appendChild(el('p', 'sub small', seated ? 'Nobody else is looking right now.' : 'Nobody else is looking right now. Ask to join a table with room, or wait for the next arrival.'));
    }

    var otherTables = s.room.tables.filter(function (t) { return !s.table || t.id !== s.table.id; });
    if (otherTables.length) {
      tables.appendChild(el('h4', null, 'Tables'));
      otherTables.forEach(function (t) {
        var box2 = el('div', 'tbl' + (t.game && t.game.playing ? ' playing' : ''));
        var head = el('div', 'tbl-head');
        head.appendChild(el('span', null, 'Table ' + t.index));
        head.appendChild(el('span', null, t.room ? 'room for one more' : 'full'));
        box2.appendChild(head);
        var row = el('div', t.room && !seated ? 'names' : 'chips');
        t.members.forEach(function (m) {
          if (t.room && !seated) row.appendChild(nameButton(m, function () { seating('ask', { player: m.id }); }));
          else row.appendChild(el('span', 'chip', m.name));
        });
        box2.appendChild(row);
        if (t.room && !seated) box2.appendChild(el('div', 'tbl-status', 'Tap a name to ask to join.'));
        tables.appendChild(box2);
      });
    }
  }

  /* ── Play ─────────────────────────────────────────────────────────────── */
  function other(pick, opened) { return [1, 2, 3].filter(function (d) { return d !== pick && d !== opened; })[0]; }

  function renderPlay(s) {
    show('phase-play');
    var g = s.game, t = s.table;
    var key = JSON.stringify([g, t, s.session.rule]);
    if (key === playKey) return;
    playKey = key;
    var role = g.role, host = role === 'host', contestant = role === 'contestant';
    document.getElementById('table-line').textContent = 'Table ' + t.index + ' · game ' + g.index;
    var badge = document.getElementById('role-badge');
    badge.className = 'badge badge-' + role;
    badge.textContent = host ? '🎤 you host' : contestant ? '🎯 you play' : '👀 you watch';
    document.getElementById('table-record').textContent = t.played ? 'At this table: ' + Show.plural(t.played, 'game') + ' played' : '';
    var prompt = document.getElementById('prompt'), panel = document.getElementById('panel'), doors = document.getElementById('doors');
    panel.innerHTML = '';
    var spec = { status: g.status, role: role, pick: g.pick, opened: g.opened, boat: g.boat, final: g.final, won: g.won,
                 mine: contestant ? 'your' : g.contestant + '\'s' };
    var text = '';
    var C = g.contestant, H = g.host;

    if (g.status === 'hiding') {
      if (host) { text = 'You\'re the host! Hide the boat behind a door. 🤫'; spec.selectable = [1, 2, 3]; spec.onSelect = function (d) { act('hide', { door: d }); }; }
      else if (contestant) text = H + ' is hiding the boat… no peeking. 👀';
      else text = H + ' is hiding the boat for ' + C + '.';
    } else if (g.status === 'picking') {
      if (host) text = 'The boat is behind door ' + g.boat + '. Keep a straight face: ' + C + ' is picking…';
      else if (contestant) { text = 'Pick a door, any door! 🚪'; spec.selectable = [1, 2, 3]; spec.onSelect = function (d) { act('pick', { door: d }); }; }
      else text = C + ' is picking a door.';
    } else if (g.status === 'opening') {
      if (host) { text = C + ' picked door ' + g.pick + '. Open a door with a goat behind it. 🐐'; spec.selectable = g.legal || []; spec.onSelect = function (d) { act('open', { door: d }); }; }
      else if (contestant) text = 'You picked door ' + g.pick + '. ' + H + ' is opening a door…';
      else text = C + ' picked door ' + g.pick + '. ' + H + ' is opening a door.';
    } else if (g.status === 'deciding') {
      var alt = other(g.pick, g.opened), rule = s.session.rule;
      if (host) text = 'Door ' + g.opened + ': a goat! Now ask ' + C + ': stay with door ' + g.pick + ', or switch to door ' + alt + '?';
      else if (contestant) {
        text = 'Door ' + g.opened + ' was a goat. Stay with door ' + g.pick + ', or switch to door ' + alt + '?';
        var choice = el('div', 'choice');
        [['stay', 'Stay with ' + g.pick], ['switch', 'Switch to ' + alt]].forEach(function (c) {
          var b = el('button', 'btn btn-' + c[0], c[1]);
          b.type = 'button';
          if (rule !== 'choice' && rule !== c[0]) b.disabled = true;
          b.addEventListener('click', function () { act('decide', { decision: c[0] }); });
          choice.appendChild(b);
        });
        panel.appendChild(choice);
        if (rule !== 'choice') panel.appendChild(el('p', 'sub small', 'House rule right now: everyone ' + (rule === 'stay' ? 'stays' : 'switches') + '.'));
      } else text = C + ' is deciding: stay with door ' + g.pick + ', or switch to door ' + alt + '?';
    } else if (g.status === 'revealed') {
      var moved = g.decision === 'switch' ? 'switched to' : 'stayed with';
      text = (contestant ? 'You ' : C + ' ') + moved + ' door ' + g.final + '…';
      var result = el('div', 'result ' + (g.won ? 'won' : 'lost'));
      if (g.won) result.textContent = contestant ? '🚤 It\'s the BOAT! You win!' : '🚤 The BOAT! ' + C + ' wins!';
      else result.textContent = contestant ? '🐐 It\'s a goat. Baaa.' : '🐐 A goat. Baaa.';
      var note = el('small', null, 'The boat was behind door ' + g.boat + '. ' + (g.pick === g.boat ? 'The first pick was right.' : 'The first pick was wrong.'));
      result.appendChild(note);
      panel.appendChild(result);
      var next = el('button', 'btn btn-primary btn-lg btn-block', 'Next game ▶');
      next.type = 'button';
      next.addEventListener('click', function () { act('next', { game: g.id }); });
      panel.appendChild(next);
      if (t.next) panel.appendChild(el('p', 'sub small', 'Next: ' + t.next.host + ' hosts, ' + t.next.contestant + ' plays.'));
      else panel.appendChild(el('p', 'sub small', 'Roles swap next game.'));
      if (g.won && celebrated !== g.id) { celebrated = g.id; Show.confetti(doors.parentNode); }
    } else {
      text = 'That game was dropped. A new one is on its way…';
    }
    prompt.textContent = text;
    Show.doors(doors, spec);
  }

  /* ── The end ──────────────────────────────────────────────────────────── */
  function stat(value, label, gold) {
    var c = el('div', 'stat-card' + (gold ? ' stat-gold' : ''));
    c.appendChild(el('div', 'stat-value', value));
    c.appendChild(el('div', 'stat-label', label));
    return c;
  }

  function renderEnded(s) {
    show('phase-ended');
    var votes = s.you.votes || {};
    voteBlock(document.getElementById('after-vote'), 'after', votes.after,
              'Now that you\'ve seen the record: the host opens a goat door and offers you the switch. What\'s the better move?');
    var box = document.getElementById('summary'), y = s.summary;
    if (!y || box.dataset.done) return;
    box.dataset.done = '1';
    box.innerHTML = '';
    var row = el('div', 'stats-row');
    row.appendChild(stat(String(y.played), 'games played'));
    row.appendChild(stat(String(y.hosted), 'games hosted'));
    row.appendChild(stat(String(y.stay.wins + y.switch.wins), 'boats won', true));
    box.appendChild(row);
    var hook = '';
    if (y.played) {
      var arms = [];
      if (y.stay.n) arms.push('staying won ' + y.stay.wins + ' of ' + y.stay.n);
      if (y.switch.n) arms.push('switching won ' + y.switch.wins + ' of ' + y.switch.n);
      hook = 'For you, ' + arms.join(' and ') + '. Your first pick was right ' + y.first_pick_right + ' of ' + y.played + ' time' + (y.played === 1 ? '' : 's') + '.';
    } else {
      hook = y.hosted ? 'You hosted ' + Show.plural(y.hosted, 'game') + ' and kept every secret.' : 'You didn\'t get to play this time.';
    }
    box.appendChild(el('p', 'hook', hook));
    if (y.games.length) {
      var ul = el('ul', 'games-list');
      y.games.forEach(function (g) {
        ul.appendChild(el('li', null, 'Table ' + g.table + ', game ' + g.index + ': picked ' + g.pick + ', ' +
          (g.decision === 'switch' ? 'switched to ' : 'stayed with ') + g.final + ', boat behind ' + g.boat + '. ' + (g.won ? '🚤 Boat!' : '🐐 Goat.')));
      });
      box.appendChild(ul);
    }
    var rec = el('div', 'card summary-record');
    rec.appendChild(el('h3', null, 'The class record'));
    var r = el('div');
    rec.appendChild(r);
    Show.record(r, s.record.tallies);
    if (s.record.tallies.switch.n) rec.appendChild(el('p', 'small muted mt-1 mb-0', s.record.text.switch));
    box.appendChild(rec);
  }

  function render(s) {
    renderInbox(s);
    if (s.session.status === 'ended') return renderEnded(s);
    if (s.table && s.game && s.table.members.length >= 2) return renderPlay(s);
    playKey = null;
    renderLobby(s);
  }

  document.getElementById('leave').addEventListener('click', function () {
    if (confirm('Leave this table? The game in play is dropped.')) seating('leave');
  });

  poller = Show.poll(STATE, render, 1500);
})();
