"""Account-backed and cookie-backed classroom ownership (shared with Bernoulli).

Names are display labels. Accounts recover linked profiles; guests prove their
existing seat with a private rejoin token in the signed browser cookie.
"""

import secrets

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from app import ecosystem
from app.config import REMEMBERED_PLAYERS
from app.models import Player, Session, Teacher

JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous characters


def generate_join_code(db: DBSession) -> str:
    while True:
        code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(6))
        if not db.query(Session).filter_by(join_code=code).first():
            return code


# ── Teachers ───────────────────────────────────────────────────────────────────

def current_teacher(request: Request, db: DBSession) -> Teacher | None:
    linked = ecosystem.owned(request, db, "teacher", Teacher)
    if linked:
        ecosystem.remember_binding(request)
        return linked
    teacher_id = request.session.get("teacher_id")
    if not teacher_id:
        return None
    teacher = db.query(Teacher).filter_by(id=teacher_id).first()
    return teacher if ecosystem.permitted(request, db, "teacher", teacher) else None


def login_teacher(request: Request, db: DBSession, name: str) -> Teacher:
    """Create or resume a private teacher profile; names are display labels."""
    return ecosystem.login_teacher(request, db, name)


def owns_session(teacher: Teacher | None, session: Session | None) -> bool:
    return teacher is not None and session is not None and session.teacher_id in getattr(teacher, "ecosystem_teacher_ids", [teacher.id])


# ── Players ────────────────────────────────────────────────────────────────────

def _remembered(request: Request) -> dict:
    players = request.session.get("players")
    return dict(players) if isinstance(players, dict) else {}


def current_player(request: Request, session_id: str, db: DBSession) -> Player | None:
    linked = ecosystem.owned(request, db, "player", Player, session_id)
    if linked:
        ecosystem.remember_binding(request)
        return linked
    entry = _remembered(request).get(session_id)
    if not entry:
        return None
    player = db.query(Player).filter_by(id=entry.get("id"), session_id=session_id).first()
    if (player is None or player.rejoin_token != entry.get("token")
            or not ecosystem.permitted(request, db, "player", player)):
        return None
    return player


def join_as_player(request: Request, db: DBSession, session: Session, name: str) -> Player | None:
    """Recover the same seat by account or browser proof, never by name alone."""
    ecosystem.lock_profiles(db)
    name = ecosystem.display_name(request, name)
    user = ecosystem.account(request)
    linked = ecosystem.owned(request, db, "player", Player, session.id)
    existing = linked or current_player(request, session.id, db)
    if not user and db.query(Player).filter_by(session_id=session.id, name=name).filter(
            Player.id != (existing.id if existing else '')).first():
        return None
    if existing:
        player = existing
        player.name = name
        if user and user['kind'] == 'guest':
            ecosystem.bind(request, db, 'player', player)
        db.commit()
    else:
        player = Player(session_id=session.id, name=name, rejoin_token=secrets.token_hex(16))
        db.add(player)
        db.flush()
        ecosystem.bind(request, db, "player", player)
        db.commit()
        db.refresh(player)

    ecosystem.remember_binding(request)
    players = _remembered(request)
    players.pop(session.id, None)
    players[session.id] = {"id": player.id, "token": player.rejoin_token}
    while len(players) > REMEMBERED_PLAYERS:
        players.pop(next(iter(players)))  # dicts keep insertion order: drop the oldest seat
    request.session["players"] = players
    return player
