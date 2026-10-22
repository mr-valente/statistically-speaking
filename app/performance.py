"""Finalized Full Monty results for the shared performance contract: one record per game a
Google-linked student played as contestant, once it is revealed."""
from datetime import timezone
from app.ecosystem import AccountLink
from app.models import Player, Session
from app.experiences.full_monty.models import FullMontyGame, FullMontyTable


def snapshots(db, session_ids=None):
    query = (db.query(FullMontyGame, FullMontyTable, Player, AccountLink, Session)
             .join(FullMontyTable, FullMontyTable.id == FullMontyGame.table_id)
             .join(Player, Player.id == FullMontyGame.contestant_id)
             .join(AccountLink, AccountLink.local_id == Player.id)
             .join(Session, Session.id == FullMontyGame.session_id)
             .filter(AccountLink.role == 'player', AccountLink.kind == 'google',
                     FullMontyGame.status == 'revealed'))
    if session_ids is not None:
        query = query.filter(Session.id.in_(session_ids))
    for game, table, player, link, session in query:
        yield {
            'source_id': 'full-monty:' + game.id, 'user_id': link.account_id,
            'activity': 'full_monty',
            'occurred_at': (game.revealed_at or game.created_at).replace(tzinfo=timezone.utc).isoformat(),
            'metrics': {'decision': game.decision, 'won': bool(game.won),
                        'first_pick_right': game.pick == game.boat},
            'context': {'classroom_id': session.id, 'table': table.index, 'game': game.index,
                        'rule': game.rule},
        }
