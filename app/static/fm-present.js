/* Full Monty projector view: join screen, the live record, the final answer. */
(function () {
  'use strict';
  var root = document.getElementById('presenter');
  var phase = null, lastKey = null;
  var RULES = { choice: 'Contestants choose: stay or switch.', stay: 'Rule right now: everyone stays.', switch: 'Rule right now: everyone switches.' };

  function show(id) {
    if (phase === id) return;
    phase = id;
    document.querySelectorAll('.phase').forEach(function (p) { p.hidden = p.id !== id; });
  }

  function render(s) {
    var r = s.record;
    if (s.session.status === 'lobby') {
      show('phase-lobby');
      document.getElementById('joined-count').textContent = s.session.players;
      document.getElementById('answered-count').textContent = r.votes.before.total;
      return;
    }
    var key = JSON.stringify([s.session, r]);
    if (key === lastKey) return;
    lastKey = key;
    if (s.session.status === 'active') {
      show('phase-active');
      document.getElementById('rule-line').textContent = RULES[s.session.rule] || '';
      Show.record(document.getElementById('record'), r.tallies);
      Show.chart(document.getElementById('chart'), r.series);
      document.getElementById('tables-line').textContent = r.tables + ' table' + (r.tables === 1 ? '' : 's') + ' playing';
      return;
    }
    show('phase-ended');
    Show.record(document.getElementById('record-final'), r.tallies);
    Show.chart(document.getElementById('chart-final'), r.series);
    var t = r.tallies, line = '';
    if (t.switch.n && t.stay.n) {
      line = 'Switching won ' + Show.pct(t.switch.rate) + ' of the time. Staying won ' + Show.pct(t.stay.rate) + '. ' + r.text.switch;
    } else if (t.games) {
      line = r.text[t.switch.n ? 'switch' : 'stay'];
    }
    document.getElementById('statement').textContent = line;
    Show.beliefs(document.getElementById('beliefs'), r.votes);
  }

  Show.poll(root.dataset.stateUrl, render, 1500);
})();
