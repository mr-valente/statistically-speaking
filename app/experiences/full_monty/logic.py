"""Full Monty game logic: tables students form themselves, one game at a time, and the class record.

The game is the classic one with the prize renamed. The host hides the boat behind one of three
doors. The contestant picks a door. The host, who knows where the boat is, opens a door the
contestant did not pick that hides a goat. The contestant stays with the first door or switches
to the other closed one. Switching wins whenever the first pick was wrong, so it wins two games
in three; staying wins the other one.

Nothing here says so to a student. The record does.
"""

from __future__ import annotations

import math
import random
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from app.experiences.full_monty.models import (FullMontyGame, FullMontyRequest, FullMontySeat, FullMontyTable,
                                               FullMontyVote, TABLE_SIZE)
from app.models import Player, Session

DOORS = (1, 2, 3)
RULES = ("choice", "stay", "switch")       # what the show lets a contestant do right now
DEFAULT_RULE = "choice"
DECISIONS = ("stay", "switch")
VOTE_CHOICES = ("switch", "stay", "same")
IN_PLAY = ("hiding", "picking", "opening", "deciding")


class Refused(ValueError):
    """A move the rules do not allow right now; the message is for the student."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Doors ──────────────────────────────────────────────────────────────────────

def legal_opens(boat: int, pick: int) -> list[int]:
    """Doors the host may open: not the contestant's, and not the boat."""
    return [d for d in DOORS if d != boat and d != pick]


def other_door(pick: int, opened: int) -> int:
    """The one closed door the contestant did not pick."""
    return next(d for d in DOORS if d != pick and d != opened)


def outcome(boat: int, pick: int, opened: int, decision: str) -> tuple[int, bool]:
    final = pick if decision == "stay" else other_door(pick, opened)
    return final, final == boat


def monty_hides() -> int:
    return secrets.choice(DOORS)


def monty_opens(boat: int, pick: int) -> int:
    return secrets.choice(legal_opens(boat, pick))


# ── Tables ─────────────────────────────────────────────────────────────────────

def tables(db: DBSession, session_id: str) -> list[FullMontyTable]:
    """Every table with someone still sitting at it, in table order."""
    return [t for t in db.query(FullMontyTable).filter_by(session_id=session_id).order_by(FullMontyTable.index.asc())
            if t.seats]


def seat_of(db: DBSession, player_id: str) -> FullMontySeat | None:
    return db.query(FullMontySeat).filter_by(player_id=player_id).first()


def table_of(db: DBSession, player_id: str) -> FullMontyTable | None:
    seat = seat_of(db, player_id)
    return seat.table if seat else None


def looking(db: DBSession, session: Session) -> list[Player]:
    """Students who have joined and are not sitting anywhere, in the order they joined."""
    seated = {s.player_id for s in db.query(FullMontySeat).filter_by(session_id=session.id)}
    return [p for p in db.query(Player).filter_by(session_id=session.id).order_by(Player.created_at.asc())
            if p.id not in seated]


def _new_table(db: DBSession, session: Session) -> FullMontyTable:
    last = db.query(FullMontyTable).filter_by(session_id=session.id).order_by(FullMontyTable.index.desc()).first()
    table = FullMontyTable(session_id=session.id, index=(last.index + 1) if last else 1)
    db.add(table)
    db.flush()
    return table


def _sit(db: DBSession, session: Session, table: FullMontyTable, player_id: str) -> None:
    position = max([s.position for s in table.seats], default=0) + 1
    db.add(FullMontySeat(session_id=session.id, table_id=table.id, player_id=player_id, position=position))
    db.flush()
    db.refresh(table)


def _settle(db: DBSession, session: Session, table: FullMontyTable | None) -> None:
    """After seats change: a playing table keeps playing; a table that lost a player drops its game."""
    if table is None:
        return
    db.refresh(table)
    game = current_game(db, table)
    if game is not None and game.status in IN_PLAY and not (
            game.host_id in table.player_ids and game.contestant_id in table.player_ids):
        game.status = "void"
        db.flush()
    if session.status == "active":
        ensure_game(db, table)


# ── Requests ───────────────────────────────────────────────────────────────────

def _pending(db: DBSession, session_id: str) -> list[FullMontyRequest]:
    return (db.query(FullMontyRequest).filter_by(session_id=session_id, status="pending")
            .order_by(FullMontyRequest.created_at.asc()).all())


def _resolve(req: FullMontyRequest, status: str) -> None:
    req.status, req.resolved_at = status, _now()


def _why_not(db: DBSession, from_id: str, to_id: str) -> str | None:
    """Why two students cannot sit together right now, or None if they can."""
    if from_id == to_id:
        return "That's you."
    mine, theirs = table_of(db, from_id), table_of(db, to_id)
    if mine is not None and theirs is not None:
        return "You already have a table." if mine.id == theirs.id else "They already have a table."
    if mine is not None and not mine.room:
        return "Your table is full."
    if theirs is not None and not theirs.room:
        return "That table is full."
    return None


def expire_stale(db: DBSession, session: Session) -> None:
    """Drop pending requests that seating changes have made impossible."""
    changed = False
    for req in _pending(db, session.id):
        if _why_not(db, req.from_id, req.to_id) is not None:
            _resolve(req, "expired")
            changed = True
    if changed:
        db.commit()


def ask_to_sit(db: DBSession, session: Session, player: Player, target_id: str) -> FullMontyRequest:
    """Ask another student to sit together. A student has one outgoing request at a time."""
    if session.status == "ended":
        raise Refused("The show is over.")
    target = db.query(Player).filter_by(id=target_id, session_id=session.id).first()
    if target is None:
        raise Refused("That student isn't in this show.")
    reason = _why_not(db, player.id, target.id)
    if reason:
        raise Refused(reason)
    for req in _pending(db, session.id):
        if req.from_id == player.id:
            _resolve(req, "cancelled")
        elif req.from_id == target.id and req.to_id == player.id:
            # They already asked us: that is a yes.
            return answer(db, session, player, req.id, True)
    req = FullMontyRequest(session_id=session.id, from_id=player.id, to_id=target.id)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def cancel_ask(db: DBSession, session: Session, player: Player) -> None:
    for req in _pending(db, session.id):
        if req.from_id == player.id:
            _resolve(req, "cancelled")
    db.commit()


def answer(db: DBSession, session: Session, player: Player, request_id: str, accept: bool) -> FullMontyRequest:
    """Accept or decline a request addressed to this student. Accepting seats both at one table."""
    req = db.query(FullMontyRequest).filter_by(id=request_id, session_id=session.id, status="pending").first()
    if req is None or req.to_id != player.id:
        raise Refused("That request is gone.")
    if not accept:
        _resolve(req, "declined")
        db.commit()
        return req
    if session.status == "ended":
        raise Refused("The show is over.")
    reason = _why_not(db, req.from_id, req.to_id)
    if reason:
        _resolve(req, "expired")
        db.commit()
        raise Refused("Too late: " + reason[0].lower() + reason[1:])
    mine, theirs = table_of(db, player.id), table_of(db, req.from_id)
    if mine is not None:
        table, newcomer = mine, req.from_id
    elif theirs is not None:
        table, newcomer = theirs, player.id
    else:
        table = _new_table(db, session)
        _sit(db, session, table, req.from_id)
        newcomer = player.id
    _sit(db, session, table, newcomer)
    _resolve(req, "accepted")
    # Whoever just sat down no longer needs their other requests.
    for other in _pending(db, session.id):
        if other.id != req.id and (other.from_id in (player.id, req.from_id)):
            _resolve(other, "cancelled")
    _settle(db, session, table)
    db.commit()
    expire_stale(db, session)
    return req


def leave_table(db: DBSession, session: Session, player: Player) -> None:
    """Stand up. A game in play at the table is dropped; whoever is left keeps the table."""
    seat = seat_of(db, player.id)
    if seat is None:
        raise Refused("You're not at a table.")
    table = seat.table
    db.delete(seat)
    db.flush()
    _settle(db, session, table)
    db.commit()
    expire_stale(db, session)


def seat_everyone(db: DBSession, session: Session) -> int:
    """The teacher's broom: sit everyone still looking. Pairs first; a leftover joins a table with room."""
    if session.status == "ended":
        return 0
    players = looking(db, session)
    random.shuffle(players)
    seated = 0
    while len(players) >= 2:
        table = _new_table(db, session)
        size = 3 if len(players) == 3 else 2
        group, players = players[:size], players[size:]
        for p in group:
            _sit(db, session, table, p.id)
            seated += 1
        _settle(db, session, table)
    if players:
        open_tables = sorted((t for t in tables(db, session.id) if t.room), key=lambda t: (len(t.seats), t.index))
        table = open_tables[0] if open_tables else _new_table(db, session)
        _sit(db, session, table, players[0].id)
        seated += 1
        _settle(db, session, table)
    db.commit()
    expire_stale(db, session)
    return seated


def start_show(db: DBSession, session: Session) -> None:
    """Lobby to active: every table with two or three students gets its first game."""
    if session.status != "lobby":
        return
    session.status = "active"
    db.flush()
    for table in tables(db, session.id):
        ensure_game(db, table)
    db.commit()


# ── Games ──────────────────────────────────────────────────────────────────────

def current_game(db: DBSession, table: FullMontyTable) -> FullMontyGame | None:
    return (db.query(FullMontyGame).filter_by(table_id=table.id)
            .order_by(FullMontyGame.index.desc()).first())


def roles_for(index: int, player_ids: list[str]) -> tuple[str, str]:
    """Game ``index`` at a table: the host and the contestant walk around the table together.

    Two students alternate. Three take turns hosting, playing, and watching, so every pair plays."""
    n = len(player_ids)
    return player_ids[(index - 1) % n], player_ids[index % n]


def ensure_game(db: DBSession, table: FullMontyTable) -> FullMontyGame | None:
    """The next game at a table, if it has partners and no game in play."""
    db.refresh(table)
    ids = table.player_ids
    if len(ids) < 2:
        return None
    latest = current_game(db, table)
    if latest is not None and latest.status in IN_PLAY:
        return latest
    index = (latest.index + 1) if latest else 1
    host, contestant = roles_for(index, ids)
    game = FullMontyGame(session_id=table.session_id, table_id=table.id, index=index,
                         host_id=host, contestant_id=contestant)
    db.add(game)
    db.flush()
    return game


def role_of(game: FullMontyGame, player_id: str) -> str | None:
    if game.host_id == player_id:
        return "host"
    if game.contestant_id == player_id:
        return "contestant"
    return None


def hide_boat(db: DBSession, game: FullMontyGame, player: Player, door: int) -> None:
    if role_of(game, player.id) != "host" or game.status != "hiding":
        raise Refused("It's not your turn to hide the boat.")
    if door not in DOORS:
        raise Refused("Pick door 1, 2 or 3.")
    game.boat, game.status = door, "picking"
    db.commit()


def pick_door(db: DBSession, game: FullMontyGame, player: Player, door: int) -> None:
    if role_of(game, player.id) != "contestant" or game.status != "picking":
        raise Refused("It's not your turn to pick a door.")
    if door not in DOORS:
        raise Refused("Pick door 1, 2 or 3.")
    game.pick, game.status = door, "opening"
    db.commit()


def open_door(db: DBSession, game: FullMontyGame, player: Player, door: int) -> None:
    if role_of(game, player.id) != "host" or game.status != "opening":
        raise Refused("It's not your turn to open a door.")
    if door == game.pick:
        raise Refused("That's the contestant's door. Open one of the others.")
    if door == game.boat:
        raise Refused("That door hides the boat! Open a goat.")
    if door not in DOORS:
        raise Refused("Pick door 1, 2 or 3.")
    game.opened, game.status = door, "deciding"
    db.commit()


def decide(db: DBSession, game: FullMontyGame, player: Player, decision: str, rule: str) -> None:
    if role_of(game, player.id) != "contestant" or game.status != "deciding":
        raise Refused("It's not your decision right now.")
    if decision not in DECISIONS:
        raise Refused("Stay or switch.")
    if rule != "choice" and decision != rule:
        raise Refused(f"The house rule right now is to {rule}.")
    game.decision, game.rule = decision, rule
    game.final, game.won = outcome(game.boat, game.pick, game.opened, decision)
    game.status, game.revealed_at = "revealed", _now()
    db.commit()


def next_game(db: DBSession, game: FullMontyGame, player: Player) -> FullMontyGame:
    """Anyone at the table starts the next game once this one is revealed; a second tap changes nothing."""
    if player.id not in game.table.player_ids:
        raise Refused("This isn't your table.")
    if game.status != "revealed":
        raise Refused("Finish this game first.")
    started = ensure_game(db, game.table)
    db.commit()
    return started


def set_rule(db: DBSession, session: Session, rule: str) -> None:
    if rule in RULES and session.status != "ended":
        session.update_settings(rule=rule)
        db.commit()


def end_session(db: DBSession, session: Session) -> None:
    """Close the show; a game still in play is dropped and leaves no mark on the record."""
    for game in db.query(FullMontyGame).filter_by(session_id=session.id):
        if game.status in IN_PLAY:
            game.status = "void"
    for req in _pending(db, session.id):
        _resolve(req, "expired")
    session.status, session.ended_at = "ended", _now()
    db.commit()


# ── Beliefs ────────────────────────────────────────────────────────────────────

def has_played(db: DBSession, player_id: str) -> bool:
    table = table_of(db, player_id)
    return table is not None and current_game(db, table) is not None


def cast_vote(db: DBSession, session: Session, player: Player, phase: str, choice: str) -> FullMontyVote:
    """``before`` is open until the student's table starts playing; ``after`` opens when the show ends."""
    if choice not in VOTE_CHOICES:
        raise Refused("Choose switch, stay or no difference.")
    if phase == "before":
        if session.status == "ended" or has_played(db, player.id):
            raise Refused("The first question closed when your table started playing.")
    elif phase == "after":
        if session.status != "ended":
            raise Refused("The second question comes at the end.")
    else:
        raise Refused("Unknown question.")
    vote = db.query(FullMontyVote).filter_by(player_id=player.id, phase=phase).first()
    if vote is None:
        vote = FullMontyVote(session_id=session.id, player_id=player.id, phase=phase, choice=choice)
        db.add(vote)
    else:
        vote.choice = choice
    db.commit()
    db.refresh(vote)
    return vote


def votes_summary(db: DBSession, session_id: str) -> dict:
    out = {phase: {c: 0 for c in VOTE_CHOICES} | {"total": 0} for phase in ("before", "after")}
    for vote in db.query(FullMontyVote).filter_by(session_id=session_id):
        out[vote.phase][vote.choice] += 1
        out[vote.phase]["total"] += 1
    return out


# ── The record ─────────────────────────────────────────────────────────────────

def revealed_games(db: DBSession, session_id: str) -> list[FullMontyGame]:
    return (db.query(FullMontyGame).filter_by(session_id=session_id, status="revealed")
            .order_by(FullMontyGame.revealed_at.asc(), FullMontyGame.created_at.asc()).all())


def tallies(games: list[FullMontyGame]) -> dict:
    out = {"games": len(games), "first_pick_right": 0,
           "stay": {"n": 0, "wins": 0}, "switch": {"n": 0, "wins": 0}}
    for g in games:
        arm = out[g.decision]
        arm["n"] += 1
        arm["wins"] += 1 if g.won else 0
        out["first_pick_right"] += 1 if g.pick == g.boat else 0
    for arm in (out["stay"], out["switch"]):
        arm["rate"] = (arm["wins"] / arm["n"]) if arm["n"] else None
        arm["surprise"] = no_effect_surprise(arm["wins"], arm["n"])
    out["first_pick_rate"] = (out["first_pick_right"] / len(games)) if games else None
    return out


def series(games: list[FullMontyGame]) -> list[dict]:
    """The two win rates after each revealed game, in the order the games were revealed."""
    stay = switch = stay_wins = switch_wins = 0
    points = []
    for i, g in enumerate(games, 1):
        if g.decision == "stay":
            stay += 1
            stay_wins += 1 if g.won else 0
        else:
            switch += 1
            switch_wins += 1 if g.won else 0
        points.append({"game": i,
                       "stay": (stay_wins / stay) if stay else None,
                       "switch": (switch_wins / switch) if switch else None})
    return points


def no_effect_surprise(wins: int, n: int) -> float | None:
    """If the decision made no difference, the chance of winning at least this often in n games."""
    if n == 0:
        return None
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n


def describe_surprise(decision: str, wins: int, n: int) -> str:
    """Plain English for how often a coin flip would do at least this well."""
    prob = no_effect_surprise(wins, n)
    if prob is None:
        return f"Nobody has {'switched' if decision == 'switch' else 'stayed'} yet."
    verb = "switching" if decision == "switch" else "staying"
    head = f"If {verb} made no difference, winning at least {wins} of {n} would happen"
    if prob >= 0.5:
        return f"{head} more than half the time."
    if prob >= 0.2:
        return f"{head} about {round(prob * 100)}% of the time."
    one_in = round(1 / prob) if prob > 0 else None
    if one_in is None or one_in > 1_000_000:
        return f"{head} less than once in a million tries."
    pct = f"{prob * 100:.1f}" if prob >= 0.01 else f"{prob * 100:.2f}"
    return f"{head} about {pct}% of the time, roughly 1 in {one_in:,}."


def class_summary(db: DBSession, session: Session) -> dict:
    games = revealed_games(db, session.id)
    t = tallies(games)
    return {"tallies": t, "series": series(games), "votes": votes_summary(db, session.id),
            "tables": len(tables(db, session.id)),
            "text": {arm: describe_surprise(arm, t[arm]["wins"], t[arm]["n"]) for arm in DECISIONS}}


def player_summary(db: DBSession, session: Session, player: Player) -> dict:
    games = revealed_games(db, session.id)
    mine = [g for g in games if g.contestant_id == player.id]
    hosted = sum(1 for g in games if g.host_id == player.id)
    record = tallies(mine)
    votes = {v.phase: v.choice for v in db.query(FullMontyVote).filter_by(player_id=player.id)}
    return {"played": len(mine), "hosted": hosted, "stay": record["stay"], "switch": record["switch"],
            "first_pick_right": record["first_pick_right"], "votes": votes,
            "games": [{"index": g.index, "table": g.table.index, "boat": g.boat, "pick": g.pick, "opened": g.opened,
                       "decision": g.decision, "final": g.final, "won": g.won} for g in mine]}
