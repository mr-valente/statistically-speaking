/* Full Monty against Monty. You and Monty take turns: one game you are the contestant and Monty
   hosts, the next you host and Monty plays. Everything happens in the browser; the record is kept
   in localStorage so a student can come back to it. */
(function () {
  'use strict';
  var KEY = 'fm-solo-record';
  var el = Show.el, doors = document.getElementById('doors'), prompt = document.getElementById('prompt');
  var panel = document.getElementById('panel'), stage = doors.parentNode, badge = document.getElementById('role-badge');
  var games = load(), game = null, timer = null, errorTimer = null;
  var MONTY_PACE = 1100;

  function load() {
    try { var g = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(g) ? g : []; } catch (e) { return []; }
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(games)); } catch (e) { /* private mode: play on */ } }

  function rand3() { return 1 + Math.floor(Math.random() * 3); }
  function pickOne(list) { return list[Math.floor(Math.random() * list.length)]; }
  function other(pick, opened) { return [1, 2, 3].filter(function (d) { return d !== pick && d !== opened; })[0]; }
  function goats(boat, pick) { return [1, 2, 3].filter(function (x) { return x !== boat && x !== pick; }); }

  function error(message) {
    var e = document.getElementById('error');
    clearTimeout(errorTimer);
    e.hidden = !message;
    e.textContent = message || '';
    if (message) errorTimer = setTimeout(function () { e.hidden = true; }, 5000);
  }

  /* Monty takes his turns after a beat, so the game reads like a game and not a flash. */
  function later(fn) {
    clearTimeout(timer);
    var g = game;
    timer = setTimeout(function () { if (game === g) fn(); }, MONTY_PACE);
  }

  /* ── One game ─────────────────────────────────────────────────────────── */
  function newGame() {
    clearTimeout(timer);
    error('');
    var last = games.length ? games[games.length - 1] : null;
    var contestant = last && last.contestant === 'you' ? 'monty' : 'you';
    game = { contestant: contestant, boat: null, pick: null, opened: null, decision: null, final: null, won: null,
             status: contestant === 'you' ? 'picking' : 'hiding' };
    if (contestant === 'you') game.boat = rand3();
    render();
  }

  function hide(d) {           /* you host: hide the boat, then Monty picks */
    error('');
    game.boat = d;
    game.status = 'picking';
    render();
    later(function () {
      game.pick = rand3();
      game.status = 'opening';
      render();
    });
  }

  function pick(d) {           /* you play: Monty opens a goat at once */
    error('');
    game.pick = d;
    game.opened = pickOne(goats(game.boat, d));
    game.status = 'deciding';
    render();
  }

  function open(d) {           /* you host: then Monty decides */
    error('');
    game.opened = d;
    game.status = 'deciding';
    render();
    later(function () { decide(Math.random() < 0.5 ? 'stay' : 'switch'); });
  }

  function decide(decision) {
    game.decision = decision;
    game.final = decision === 'stay' ? game.pick : other(game.pick, game.opened);
    game.won = game.final === game.boat;
    game.status = 'revealed';
    games.push({ contestant: game.contestant, boat: game.boat, pick: game.pick, opened: game.opened,
                 decision: decision, final: game.final, won: game.won });
    save();
    render();
    if (game.won) Show.confetti(stage);
  }

  /* ── The record, computed here the same way the server does it ────────── */
  function tallies() {
    var t = { games: games.length, first_pick_right: 0, stay: { n: 0, wins: 0 }, switch: { n: 0, wins: 0 } };
    games.forEach(function (g) {
      t[g.decision].n += 1;
      t[g.decision].wins += g.won ? 1 : 0;
      t.first_pick_right += g.pick === g.boat ? 1 : 0;
    });
    ['stay', 'switch'].forEach(function (a) { t[a].rate = t[a].n ? t[a].wins / t[a].n : null; });
    t.first_pick_rate = games.length ? t.first_pick_right / games.length : null;
    return t;
  }

  function series() {
    var stay = 0, sw = 0, stayW = 0, swW = 0;
    return games.map(function (g, i) {
      if (g.decision === 'stay') { stay++; stayW += g.won ? 1 : 0; } else { sw++; swW += g.won ? 1 : 0; }
      return { game: i + 1, stay: stay ? stayW / stay : null, switch: sw ? swW / sw : null };
    });
  }

  function renderRecord() {
    var t = tallies();
    Show.record(document.getElementById('record'), t);
    Show.chart(document.getElementById('chart'), series());
    var yours = games.filter(function (g) { return (g.contestant || 'you') === 'you'; }).length;
    document.getElementById('games-line').textContent = t.games ? Show.plural(t.games, 'game') + ' · you played ' + yours + ', Monty played ' + (t.games - yours) : '';
    document.getElementById('surprise').textContent = t.switch.n ? Show.describe('switch', t.switch.wins, t.switch.n) : '';
  }

  /* ── Rendering ────────────────────────────────────────────────────────── */
  function render() {
    panel.innerHTML = '';
    var you = game.contestant === 'you', host = !you;
    badge.className = 'badge badge-' + (you ? 'contestant' : 'host');
    badge.textContent = you ? '🎯 you play' : '🎤 you host';
    var spec = { status: game.status, role: you ? 'contestant' : 'host', pick: game.pick, opened: game.opened,
                 final: game.final, won: game.won, mine: you ? 'your' : 'Monty\'s' };
    if (host || game.status === 'revealed') spec.boat = game.boat;
    var text = '';

    if (game.status === 'hiding') {
      text = 'You\'re the host! Hide the boat behind a door. 🤫';
      spec.selectable = [1, 2, 3];
      spec.onSelect = hide;
    } else if (game.status === 'picking') {
      if (you) {
        text = 'Monty: "I\'ve hidden the boat. Pick a door, any door!" 🚪';
        spec.selectable = [1, 2, 3];
        spec.onSelect = pick;
      } else {
        text = 'The boat is behind door ' + game.boat + '. Keep a straight face: Monty is picking…';
      }
    } else if (game.status === 'opening') {
      text = 'Monty picked door ' + game.pick + '. Open a door with a goat behind it. 🐐';
      spec.selectable = goats(game.boat, game.pick);
      spec.onSelect = open;
      spec.refuse = function (d) {
        if (d === game.pick) return 'That\'s Monty\'s door. The host never opens the contestant\'s pick.';
        if (d === game.boat) return 'That\'s the boat! The host never gives away the prize. Open a goat.';
        return null;
      };
      spec.onRefuse = error;
    } else if (game.status === 'deciding') {
      var alt = other(game.pick, game.opened);
      if (you) {
        text = 'Monty opens door ' + game.opened + '… a goat! 🐐 Stay with door ' + game.pick + ', or switch to door ' + alt + '?';
        var choice = el('div', 'choice');
        [['stay', 'Stay with ' + game.pick], ['switch', 'Switch to ' + alt]].forEach(function (c) {
          var b = el('button', 'btn btn-' + c[0], c[1]);
          b.type = 'button';
          b.addEventListener('click', function () { decide(c[0]); });
          choice.appendChild(b);
        });
        panel.appendChild(choice);
      } else {
        text = 'Door ' + game.opened + ': a goat! Monty is deciding: stay with door ' + game.pick + ', or switch to door ' + alt + '…';
      }
    } else {
      var moved = game.decision === 'switch' ? 'switched to' : 'stayed with';
      text = (you ? 'You ' : 'Monty ') + moved + ' door ' + game.final + '…';
      var result = el('div', 'result ' + (game.won ? 'won' : 'lost'));
      if (you) result.textContent = game.won ? '🚤 It\'s the BOAT! You win!' : '🐐 It\'s a goat. Baaa.';
      else result.textContent = game.won ? '🚤 The BOAT! Monty wins this one.' : '🐐 A goat. Monty: "Baaa."';
      var note = you ? 'Monty: "The boat was behind door ' + game.boat + ' the whole time."'
                     : 'You hid it behind door ' + game.boat + '. ' + (game.pick === game.boat ? 'Monty\'s first pick was right.' : 'Monty\'s first pick was wrong.');
      result.appendChild(el('small', null, note));
      panel.appendChild(result);
      var next = el('button', 'btn btn-primary btn-lg btn-block', you ? 'Next game: you host ▶' : 'Next game: you play ▶');
      next.type = 'button';
      next.addEventListener('click', newGame);
      panel.appendChild(next);
    }
    prompt.textContent = text;
    Show.doors(doors, spec);
    renderRecord();
  }

  document.getElementById('clear').addEventListener('click', function () {
    if (!games.length || confirm('Clear the record and start fresh?')) { games = []; save(); newGame(); }
  });

  newGame();
})();
