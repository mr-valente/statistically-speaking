/* Full Monty projector view: the join screen and the room forming, the live record, the final answer. */
(function () {
  'use strict';
  var root = document.getElementById('presenter');
  var phase = null, lastKey = null;
  var RULES = { choice: 'Contestants choose: stay or switch.', stay: 'House rule right now: everyone stays.', switch: 'House rule right now: everyone switches.' };

  function show(id) {
    if (phase === id) return;
    phase = id;
    document.querySelectorAll('.phase').forEach(function (p) { p.hidden = p.id !== id; });
  }

  function render(s) {
    var r = s.record;
    var key = JSON.stringify([s.session, r, s.room]);
    if (key === lastKey) return;
    lastKey = key;
    if (s.session.status === 'lobby') {
      show('phase-lobby');
      document.getElementById('joined-count').textContent = s.session.players;
      document.getElementById('answered-count').textContent = r.votes.before.total;
      Show.room(document.getElementById('room'), s.room, s.session.status);
      return;
    }
    if (s.session.status === 'active') {
      show('phase-active');
      document.getElementById('rule-line').textContent = RULES[s.session.rule] || '';
      Show.record(document.getElementById('record'), r.tallies);
      Show.chart(document.getElementById('chart'), r.series);
      Show.room(document.getElementById('room-live'), s.room, s.session.status);
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
