"""Full Monty game logic: tables of partners, one game at a time, and the class record.

The game is the standard one. The host hides the car behind one of three doors.
The contestant picks a door. The host, who knows where the car is, opens a door
the contestant did not pick and that hides a goat. The contestant stays with
the first door or switches to the other closed one. Switching wins whenever the
first pick was wrong, so it wins two games in three; staying wins the other one.

Nothing here says so to a student. The record does.
"""

from __future__ import annotations

import math
import random
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from app.experiences.full_monty.models import FullMontyGame, FullMontyPair, FullMontyVote
from app.models import Player, Session

DOORS = (1, 2, 3)
RULES = ("choice", "stay", "switch")       # what the show lets a contestant do right now
DEFAULT_RULE = "choice"
DECISIONS = ("stay", "switch")
VOTE_CHOICES = ("switch", "stay", "same")
SWITCH_WINS, STAY_WINS = 2 / 3, 1 / 3


# ── Doors ──────────────────────────────────────────────────────────────────────

def legal_opens(car: int, pick: int) -> list[int]:
    """Doors the host may open: not the contestant's, and not the car."""
    return [d for d in DOORS if d != car and d != pick]


def other_door(pick: int, opened: int) -> int:
    """The one closed door the contestant did not pick."""
    return next(d for d in DOORS if d != pick and d != opened)


def outcome(car: int, pick: int, opened: int, decision: str) -> tuple[int, bool]:
    final = pick if decision == "stay" else other_door(pick, opened)
    return final, final == car


def house_hides() -> int:
    return secrets.choice(DOORS)


def house_opens(car: int, pick: int) -> int:
    return secrets.choice(legal_opens(car, pick))


# ── Tables ─────────────────────────────────────────────────────────────────────

def active_pairs(db: DBSession, session_id: str) -> list[FullMontyPair]:
    return (db.query(FullMontyPair).filter_by(session_id=session_id, retired=False)
            .order_by(FullMontyPair.index.asc()).all())


def pair_for(db: DBSession, session_id: str, player_id: str) -> FullMontyPair | None:
    return (db.query(FullMontyPair)
            .filter(FullMontyPair.session_id == session_id, FullMontyPair.retired.is_(False),
                    (FullMontyPair.first_id == player_id) | (FullMontyPair.second_id == player_id))
            .first())


def unpaired_players(db: DBSession, session: Session) -> list[Player]:
    seated = set()
    for pair in active_pairs(db, session.id):
        seated.update({pair.first_id, pair.second_id})
    return [p for p in db.query(Player).filter_by(session_id=session.id).order_by(Player.created_at.asc())
            if p.id not in seated]


def make_pairs(db: DBSession, session: Session, mode: str = "newcomers") -> list[FullMontyPair]:
    """Seat players at tables. ``newcomers`` seats only the unseated; ``reshuffle`` reseats everyone.

    A reshuffle retires the current tables and voids any game still in play; revealed games stay in
    the record. An odd player out is seated with the House, which hosts every game at that table.
    """
    if session.status == "ended":
        return []
    if mode == "reshuffle":
        for pair in active_pairs(db, session.id):
            pair.retired = True
            for game in pair.games:
                if game.status not in ("revealed", "void"):
                    game.status = "void"
        db.flush()
    players = unpaired_players(db, session)
    random.shuffle(players)
    last = db.query(FullMontyPair).filter_by(session_id=session.id).order_by(FullMontyPair.index.desc()).first()
    index = last.index if last else 0
    pairs = []
    for i in range(0, len(players), 2):
        index += 1
        first, second = players[i], players[i + 1] if i + 1 < len(players) else None
        pair = FullMontyPair(session_id=session.id, index=index, first_id=first.id,
                             second_id=second.id if second else None)
        db.add(pair)
        db.flush()
        start_game(db, pair)
        pairs.append(pair)
    if pairs and session.status == "lobby":
        session.status = "active"
    db.commit()
    return pairs


# ── Games ──────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def current_game(db: DBSession, pair: FullMontyPair) -> FullMontyGame | None:
    return (db.query(FullMontyGame).filter_by(pair_id=pair.id)
            .order_by(FullMontyGame.index.desc()).first())


def start_game(db: DBSession, pair: FullMontyPair) -> FullMontyGame:
    """The next game at a table. Partners swap roles each game; the House always hosts."""
    latest = current_game(db, pair)
    if latest is not None and latest.status not in ("revealed", "void"):
        return latest
    index = (latest.index + 1) if latest else 1
    if pair.house:
        host, contestant = None, pair.first_id
    elif index % 2:
        host, contestant = pair.first_id, pair.second_id
    else:
        host, contestant = pair.second_id, pair.first_id
    game = FullMontyGame(session_id=pair.session_id, pair_id=pair.id, index=index,
                         host_id=host, contestant_id=contestant)
    if pair.house:
        game.car, game.status = house_hides(), "picking"
    db.add(game)
    db.flush()
    return game


def role_of(game: FullMontyGame, player_id: str) -> str | None:
    if game.host_id == player_id:
        return "host"
    if game.contestant_id == player_id:
        return "contestant"
    return None


class Refused(ValueError):
    """A move the rules do not allow right now; the message is for the student."""


def hide_car(db: DBSession, game: FullMontyGame, player: Player, door: int) -> None:
    if role_of(game, player.id) != "host" or game.status != "hiding":
        raise Refused("It is not your turn to hide the car.")
    if door not in DOORS:
        raise Refused("Pick door 1, 2 or 3.")
    game.car, game.status = door, "picking"
    db.commit()


def pick_door(db: DBSession, game: FullMontyGame, player: Player, door: int) -> None:
    if role_of(game, player.id) != "contestant" or game.status != "picking":
        raise Refused("It is not your turn to pick a door.")
    if door not in DOORS:
        raise Refused("Pick door 1, 2 or 3.")
    game.pick, game.status = door, "opening"
    if game.house:
        game.opened, game.status = house_opens(game.car, game.pick), "deciding"
    db.commit()


def open_door(db: DBSession, game: FullMontyGame, player: Player, door: int) -> None:
    if role_of(game, player.id) != "host" or game.status != "opening":
        raise Refused("It is not your turn to open a door.")
    if door == game.pick:
        raise Refused("That is the contestant's door. Open one of the others.")
    if door == game.car:
        raise Refused("That door hides the car. Open a goat.")
    if door not in DOORS:
        raise Refused("Pick door 1, 2 or 3.")
    game.opened, game.status = door, "deciding"
    db.commit()


def decide(db: DBSession, game: FullMontyGame, player: Player, decision: str, rule: str) -> None:
    if role_of(game, player.id) != "contestant" or game.status != "deciding":
        raise Refused("It is not your decision right now.")
    if decision not in DECISIONS:
        raise Refused("Stay or switch.")
    if rule != "choice" and decision != rule:
        raise Refused(f"The rule right now is to {rule}.")
    game.decision, game.rule = decision, rule
    game.final, game.won = outcome(game.car, game.pick, game.opened, decision)
    game.status, game.revealed_at = "revealed", _now()
    db.commit()


def next_game(db: DBSession, game: FullMontyGame, player: Player) -> FullMontyGame:
    """Either partner starts the next game once this one is revealed; a second tap changes nothing."""
    if role_of(game, player.id) is None:
        raise Refused("This is not your table.")
    if game.status != "revealed":
        raise Refused("Finish this game first.")
    started = start_game(db, game.pair)
    db.commit()
    return started


def set_rule(db: DBSession, session: Session, rule: str) -> None:
    if rule in RULES and session.status != "ended":
        session.update_settings(rule=rule)
        db.commit()


def end_session(db: DBSession, session: Session) -> None:
    """Close the classroom; a game still in play is voided and leaves no mark on the record."""
    for pair in active_pairs(db, session.id):
        for game in pair.games:
            if game.status not in ("revealed", "void"):
                game.status = "void"
    session.status, session.ended_at = "ended", _now()
    db.commit()


# ── Beliefs ────────────────────────────────────────────────────────────────────

def cast_vote(db: DBSession, session: Session, player: Player, phase: str, choice: str) -> FullMontyVote:
    """``before`` is open until the student is seated; ``after`` opens when the session ends."""
    if choice not in VOTE_CHOICES:
        raise Refused("Choose switch, stay or no difference.")
    if phase == "before":
        if session.status == "ended" or pair_for(db, session.id, player.id) is not None:
            raise Refused("The first question closed when you were seated.")
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
        out["first_pick_right"] += 1 if g.pick == g.car else 0
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
            "tables": len(active_pairs(db, session.id)),
            "text": {arm: describe_surprise(arm, t[arm]["wins"], t[arm]["n"]) for arm in DECISIONS}}


def player_summary(db: DBSession, session: Session, player: Player) -> dict:
    games = revealed_games(db, session.id)
    mine = [g for g in games if g.contestant_id == player.id]
    hosted = sum(1 for g in games if g.host_id == player.id)
    record = tallies(mine)
    votes = {v.phase: v.choice for v in db.query(FullMontyVote).filter_by(player_id=player.id)}
    return {"played": len(mine), "hosted": hosted, "stay": record["stay"], "switch": record["switch"],
            "first_pick_right": record["first_pick_right"], "votes": votes,
            "games": [{"index": g.index, "table": g.pair.index, "car": g.car, "pick": g.pick, "opened": g.opened,
                       "decision": g.decision, "final": g.final, "won": g.won} for g in mine]}
