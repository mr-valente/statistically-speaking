/* Full Monty teacher dashboard: the room as it stands, the record, beliefs. */
(function () {
  'use strict';
  var root = document.getElementById('dashboard');
  var el = Show.el, rendered = root.dataset.sessionStatus, lastKey = null;
  ['rule-form', 'survey-form'].forEach(function (id) {
    var form = document.getElementById(id);
    if (form) form.addEventListener('change', function () { form.submit(); });
  });
  document.querySelectorAll('.js-hide').forEach(function (e) { e.hidden = true; });

  function apply(s) {
    if (s.session.status !== rendered) { location.reload(); return; }
    var key = JSON.stringify([s.players, s.room, s.summary]);
    if (key === lastKey) return;
    lastKey = key;

    document.getElementById('player-count').textContent = s.players.length;
    var chips = document.getElementById('player-chips');
    chips.innerHTML = '';
    s.players.forEach(function (n) { chips.appendChild(el('span', 'chip', n)); });
    document.getElementById('no-players').hidden = s.players.length > 0;

    Show.room(document.getElementById('room'), s.room, s.session.status);
    document.getElementById('no-tables').hidden = s.room.tables.length > 0 || s.room.looking.length > 0;

    Show.record(document.getElementById('record'), s.summary.tallies);
    Show.chart(document.getElementById('chart'), s.summary.series);
    document.getElementById('surprise').textContent = s.summary.tallies.switch.n ? s.summary.text.switch : '';
    var beliefs = document.getElementById('beliefs');
    if (beliefs) Show.beliefs(beliefs, s.summary.votes);
  }

  Show.poll(root.dataset.stateUrl, apply, rendered === 'ended' ? 0 : 2000);
})();
