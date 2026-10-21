/* Full Monty teacher dashboard: live tables, the record, beliefs. */
(function () {
  'use strict';
  var root = document.getElementById('dashboard');
  var el = Show.el, rendered = root.dataset.sessionStatus, lastKey = null;
  Show.confirmForms();
  Show.qrDialog();
  var ruleForm = document.getElementById('rule-form');
  if (ruleForm) ruleForm.addEventListener('change', function () { ruleForm.submit(); });

  function apply(s) {
    if (s.session.status !== rendered) { location.reload(); return; }
    var key = JSON.stringify([s.players, s.tables, s.unpaired, s.summary]);
    if (key === lastKey) return;
    lastKey = key;

    document.getElementById('player-count').textContent = s.players.length;
    var chips = document.getElementById('player-chips');
    chips.innerHTML = '';
    s.players.forEach(function (n) { chips.appendChild(el('span', 'chip', n)); });
    document.getElementById('no-players').hidden = s.players.length > 0;

    var body = document.querySelector('#tables tbody');
    body.innerHTML = '';
    s.tables.forEach(function (t) {
      var tr = el('tr');
      tr.appendChild(el('td', null, String(t.index)));
      tr.appendChild(el('td', null, t.first + ' · ' + t.second));
      tr.appendChild(el('td', null, String(t.played)));
      tr.appendChild(el('td', 'muted', t.game ? t.game.status + ' · ' + t.game.host + ' hosts' : ''));
      body.appendChild(tr);
    });
    document.getElementById('no-tables').hidden = s.tables.length > 0;
    document.getElementById('unpaired-line').hidden = s.unpaired.length === 0;
    document.getElementById('unpaired').textContent = s.unpaired.join(', ');

    Show.record(document.getElementById('record'), s.summary.tallies);
    Show.chart(document.getElementById('chart'), s.summary.series);
    document.getElementById('surprise').textContent = s.summary.tallies.switch.n ? s.summary.text.switch : '';
    Show.beliefs(document.getElementById('beliefs'), s.summary.votes);
  }

  Show.poll(root.dataset.stateUrl, apply, rendered === 'ended' ? 0 : 2000);
})();
