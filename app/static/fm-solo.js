/* Full Monty against Monty, the computer host. Everything happens in the browser; the record is kept
   in localStorage so a student can come back to it. */
(function () {
  'use strict';
  var KEY = 'fm-solo-record';
  var el = Show.el, doors = document.getElementById('doors'), prompt = document.getElementById('prompt');
  var panel = document.getElementById('panel'), stage = doors.parentNode;
  var games = load(), game = null;

  function load() {
    try { var g = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(g) ? g : []; } catch (e) { return []; }
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(games)); } catch (e) { /* private mode: play on */ } }

  function rand3() { return 1 + Math.floor(Math.random() * 3); }
  function other(pick, opened) { return [1, 2, 3].filter(function (d) { return d !== pick && d !== opened; })[0]; }

  function newGame() {
    game = { boat: rand3(), pick: null, opened: null, decision: null, final: null, won: null, status: 'picking' };
    render();
  }

  function pick(d) {
    game.pick = d;
    var goats = [1, 2, 3].filter(function (x) { return x !== game.boat && x !== d; });
    game.opened = goats[Math.floor(Math.random() * goats.length)];
    game.status = 'deciding';
    render();
  }

  function decide(decision) {
    game.decision = decision;
    game.final = decision === 'stay' ? game.pick : other(game.pick, game.opened);
    game.won = game.final === game.boat;
    game.status = 'revealed';
    games.push({ boat: game.boat, pick: game.pick, opened: game.opened, decision: decision, final: game.final, won: game.won });
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
    document.getElementById('games-line').textContent = t.games ? Show.plural(t.games, 'game') + ' so far' : '';
    document.getElementById('surprise').textContent = t.switch.n ? Show.describe('switch', t.switch.wins, t.switch.n) : '';
  }

  function render() {
    panel.innerHTML = '';
    var spec = { status: game.status, role: 'contestant', pick: game.pick, opened: game.opened, final: game.final, won: game.won, mine: 'your' };
    if (game.status === 'revealed') spec.boat = game.boat;
    if (game.status === 'picking') {
      prompt.textContent = 'Monty: "I\'ve hidden the boat. Pick a door, any door!" 🚪';
      spec.selectable = [1, 2, 3];
      spec.onSelect = pick;
    } else if (game.status === 'deciding') {
      var alt = other(game.pick, game.opened);
      prompt.textContent = 'Monty opens door ' + game.opened + '… a goat! 🐐 Stay with door ' + game.pick + ', or switch to door ' + alt + '?';
      var choice = el('div', 'choice');
      [['stay', 'Stay with ' + game.pick], ['switch', 'Switch to ' + alt]].forEach(function (c) {
        var b = el('button', 'btn btn-' + c[0], c[1]);
        b.type = 'button';
        b.addEventListener('click', function () { decide(c[0]); });
        choice.appendChild(b);
      });
      panel.appendChild(choice);
    } else {
      prompt.textContent = 'You ' + (game.decision === 'switch' ? 'switched to' : 'stayed with') + ' door ' + game.final + '…';
      var result = el('div', 'result ' + (game.won ? 'won' : 'lost'));
      result.textContent = game.won ? '🚤 It\'s the BOAT! You win!' : '🐐 It\'s a goat. Baaa.';
      result.appendChild(el('small', null, 'Monty: "The boat was behind door ' + game.boat + ' the whole time."'));
      panel.appendChild(result);
      var next = el('button', 'btn btn-primary btn-lg btn-block', 'Play again ▶');
      next.type = 'button';
      next.addEventListener('click', newGame);
      panel.appendChild(next);
    }
    Show.doors(doors, spec);
    renderRecord();
  }

  document.getElementById('clear').addEventListener('click', function () {
    if (!games.length || confirm('Clear your record and start fresh?')) { games = []; save(); renderRecord(); }
  });

  newGame();
})();
