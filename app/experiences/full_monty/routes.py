"""Full Monty routes: teacher controls, projector view, student play, solo play, and live state."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app import ecosystem
from app.database import get_db
from app.identity import current_player, current_teacher, generate_join_code, owns_session
from app.models import Player, Session
from app.templating import templates
from app.experiences.full_monty import logic
from app.experiences.full_monty.models import FullMontyGame, FullMontyTable, FullMontyVote, TABLE_SIZE

router = APIRouter()

KIND = "full_monty"
NO_STORE = {"Cache-Control": "no-store"}


def _epoch(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _teacher_session(request: Request, session_id: str, db: DBSession):
    teacher = current_teacher(request, db)
    session = db.query(Session).filter_by(id=session_id, kind=KIND).first()
    if not owns_session(teacher, session):
        return teacher, None
    return teacher, session


def _redirect_teacher(request: Request, session_id: str):
    return RedirectResponse(url=request.url_for("full_monty_teacher", session_id=session_id), status_code=303)


def _guard(request: Request, session_id: str, db: DBSession):
    """Shared preamble for teacher POST actions: returns session or a redirect."""
    teacher, session = _teacher_session(request, session_id, db)
    if teacher is None:
        return None, RedirectResponse(url=request.url_for("admin_login_page"), status_code=303)
    if session is None:
        return None, RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)
    return session, None


def _rule(session: Session) -> str:
    rule = session.settings.get("rule", logic.DEFAULT_RULE)
    return rule if rule in logic.RULES else logic.DEFAULT_RULE


# ── Solo play ──────────────────────────────────────────────────────────────────

@router.get("/solo", response_class=HTMLResponse)
def full_monty_solo(request: Request):
    """Play against Monty, the computer host. No session, no sign-in; the record lives in the browser."""
    return templates.TemplateResponse(request=request, name="full_monty/solo.html", context={"request": request})


# ── Create ─────────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
def full_monty_new(request: Request, db: DBSession = Depends(get_db)):
    teacher = current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url=request.url_for("admin_login_page"), status_code=303)
    return templates.TemplateResponse(request=request, name="full_monty/new.html",
                                      context={"request": request, "teacher": teacher})


@router.post("/create")
def full_monty_create(request: Request, label: str = Form(""), db: DBSession = Depends(get_db)):
    teacher = current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url=request.url_for("admin_login_page"), status_code=303)
    settings = {"label": " ".join(label.split())[:40], "rule": logic.DEFAULT_RULE}
    session = Session(teacher_id=teacher.id, kind=KIND, join_code=generate_join_code(db),
                      settings_json=json.dumps(settings))
    db.add(session)
    db.commit()
    db.refresh(session)
    return _redirect_teacher(request, session.id)


# ── Shared views of the room ───────────────────────────────────────────────────

def _names(db: DBSession, session_id: str) -> dict[str, str]:
    return {p.id: p.name for p in db.query(Player).filter_by(session_id=session_id)}


def _room(db: DBSession, session: Session, names: dict[str, str]) -> dict:
    """The tables as they stand and who is still looking: what everyone, projector included, may see."""
    out = []
    for table in logic.tables(db, session.id):
        game = logic.current_game(db, table)
        playing = game is not None and game.status in logic.IN_PLAY
        out.append({
            "id": table.id, "index": table.index, "room": table.room, "size": TABLE_SIZE,
            "members": [{"id": pid, "name": names.get(pid, "?")} for pid in table.player_ids],
            "played": sum(1 for g in table.games if g.status == "revealed"),
            "game": None if game is None else {
                "index": game.index, "status": game.status, "playing": playing,
                "host": names.get(game.host_id, "?"), "contestant": names.get(game.contestant_id, "?")},
        })
    return {"tables": out, "looking": [{"id": p.id, "name": p.name} for p in logic.looking(db, session)]}


@router.get("/t/{session_id}", response_class=HTMLResponse)
def full_monty_teacher(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    teacher, session = _teacher_session(request, session_id, db)
    if teacher is None:
        return RedirectResponse(url=request.url_for("admin_login_page"), status_code=303)
    if session is None:
        return RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)
    names = _names(db, session.id)
    return templates.TemplateResponse(request=request, name="full_monty/teacher.html", context={
        "request": request, "teacher": teacher, "session": session, "settings": session.settings,
        "rule": _rule(session), "rules": logic.RULES, "players": list(names.values()),
        "room": _room(db, session, names), "summary": logic.class_summary(db, session),
        "join_url": str(request.url_for("join_form")),
        "qr_url": str(request.url_for("join_qr", code=session.join_code)),
        "state_url": str(request.url_for("full_monty_teacher_state", session_id=session.id)),
    })


@router.get("/t/{session_id}/state")
def full_monty_teacher_state(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """Live numbers for the teacher page: the room as it stands, and the record so far."""
    teacher, session = _teacher_session(request, session_id, db)
    if session is None:
        return JSONResponse({"error": "not_found"}, status_code=404, headers=NO_STORE)
    names = _names(db, session.id)
    return JSONResponse({
        "session": {"status": session.status, "rule": _rule(session), "players": len(names)},
        "players": list(names.values()), "room": _room(db, session, names),
        "summary": logic.class_summary(db, session), "now": _epoch(datetime.now(timezone.utc)),
    }, headers=NO_STORE)


# ── Teacher actions ────────────────────────────────────────────────────────────

@router.post("/t/{session_id}/start")
def full_monty_start(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    session, redirect = _guard(request, session_id, db)
    if redirect:
        return redirect
    logic.start_show(db, session)
    return _redirect_teacher(request, session_id)


@router.post("/t/{session_id}/seat")
def full_monty_seat(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    session, redirect = _guard(request, session_id, db)
    if redirect:
        return redirect
    logic.seat_everyone(db, session)
    return _redirect_teacher(request, session_id)


@router.post("/t/{session_id}/rule")
def full_monty_rule(session_id: str, request: Request, rule: str = Form(...), db: DBSession = Depends(get_db)):
    session, redirect = _guard(request, session_id, db)
    if redirect:
        return redirect
    logic.set_rule(db, session, rule)
    return _redirect_teacher(request, session_id)


@router.post("/t/{session_id}/end")
def full_monty_end(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    session, redirect = _guard(request, session_id, db)
    if redirect:
        return redirect
    if session.status != "ended":
        logic.end_session(db, session)
    return _redirect_teacher(request, session_id)


# ── Export ─────────────────────────────────────────────────────────────────────

def _csv(rows: list[list], filename: str) -> StreamingResponse:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/t/{session_id}/export")
def full_monty_export(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """One row per game, revealed or dropped, in table order."""
    session, redirect = _guard(request, session_id, db)
    if redirect:
        return redirect
    names = _names(db, session.id)
    games = (db.query(FullMontyGame).join(FullMontyTable, FullMontyTable.id == FullMontyGame.table_id)
             .filter(FullMontyGame.session_id == session.id)
             .order_by(FullMontyTable.index.asc(), FullMontyGame.index.asc()).all())
    rows = [["table", "game", "host", "contestant", "status", "boat", "pick", "opened", "decision", "final", "won",
             "first_pick_right", "rule", "revealed_at"]]
    for g in games:
        rows.append([g.table.index, g.index, names.get(g.host_id, "?"), names.get(g.contestant_id, "?"),
                     g.status, g.boat, g.pick, g.opened, g.decision, g.final,
                     "" if g.won is None else g.won, "" if g.pick is None or g.boat is None else g.pick == g.boat,
                     g.rule or "", g.revealed_at.isoformat() if g.revealed_at else ""])
    return _csv(rows, f"full_monty_{session.join_code}.csv")


@router.get("/t/{session_id}/export/votes")
def full_monty_export_votes(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """One row per student: what they believed before and after."""
    session, redirect = _guard(request, session_id, db)
    if redirect:
        return redirect
    votes = {}
    for v in db.query(FullMontyVote).filter_by(session_id=session.id):
        votes.setdefault(v.player_id, {})[v.phase] = v.choice
    rows = [["student", "before", "after"]]
    for p in db.query(Player).filter_by(session_id=session.id).order_by(Player.created_at.asc()):
        rows.append([p.name, votes.get(p.id, {}).get("before", ""), votes.get(p.id, {}).get("after", "")])
    return _csv(rows, f"full_monty_{session.join_code}_beliefs.csv")


# ── Presenter (projector) ──────────────────────────────────────────────────────

@router.get("/p/{session_id}", response_class=HTMLResponse)
def full_monty_present(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """A full-screen view for the projector. Shows only what students may see."""
    session = db.query(Session).filter_by(id=session_id, kind=KIND).first()
    if session is None:
        return RedirectResponse(url=request.url_for("home"), status_code=303)
    return templates.TemplateResponse(request=request, name="full_monty/present.html", context={
        "request": request, "session": session, "settings": session.settings,
        "join_url": str(request.url_for("join_form")),
        "qr_url": str(request.url_for("join_qr", code=session.join_code)),
        "state_url": str(request.url_for("full_monty_public_state", session_id=session.id)),
    })


# ── Student ────────────────────────────────────────────────────────────────────

@router.get("/s/{session_id}", response_class=HTMLResponse)
def full_monty_student(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter_by(id=session_id, kind=KIND).first()
    player = current_player(request, session_id, db) if session else None
    if session is None or player is None:
        return RedirectResponse(url=request.url_for("join_form"), status_code=303)
    return templates.TemplateResponse(request=request, name="full_monty/student.html", context={
        "request": request, "session": session, "settings": session.settings, "player": player,
        "state_url": str(request.url_for("full_monty_public_state", session_id=session.id)),
        "act_url": str(request.url_for("full_monty_act", session_id=session.id)),
        "seat_url": str(request.url_for("full_monty_seating", session_id=session.id)),
        "vote_url": str(request.url_for("full_monty_vote", session_id=session.id)),
        "solo_url": str(request.url_for("full_monty_solo")),
    })


def _game_view(game: FullMontyGame, player: Player | None, names: dict[str, str]) -> dict:
    """What one viewer may know about a game. The boat is the host's secret until the reveal."""
    role = logic.role_of(game, player.id) if player else None
    if role is None and player is not None and player.id in game.table.player_ids:
        role = "watching"
    view = {"id": game.id, "index": game.index, "status": game.status, "role": role,
            "host": names.get(game.host_id, "?"), "contestant": names.get(game.contestant_id, "?"),
            "pick": game.pick, "opened": game.opened, "decision": game.decision, "rule": game.rule}
    if game.status in ("revealed", "void") or role == "host":
        view["boat"] = game.boat
    if game.status == "revealed":
        view["final"], view["won"] = game.final, game.won
    if role == "host" and game.status == "opening":
        view["legal"] = logic.legal_opens(game.boat, game.pick)
    return view


def _public_state(db: DBSession, session: Session, player: Player | None) -> dict:
    """What every student and the projector may know right now."""
    logic.expire_stale(db, session)
    names = _names(db, session.id)
    state = {
        "session": {"status": session.status, "join_code": session.join_code, "rule": _rule(session),
                    "label": session.settings.get("label", ""), "players": len(names)},
        "room": _room(db, session, names),
        "you": None, "table": None, "game": None, "summary": None,
        "record": logic.class_summary(db, session),
        "now": _epoch(datetime.now(timezone.utc)),
    }
    if player is None:
        return state
    votes = {v.phase: v.choice for v in db.query(FullMontyVote).filter_by(player_id=player.id)}
    pending = logic._pending(db, session.id)
    state["you"] = {
        "id": player.id, "name": player.name, "votes": votes,
        "asked": next(({"id": r.id, "to": names.get(r.to_id, "?")} for r in pending if r.from_id == player.id), None),
        "inbox": [{"id": r.id, "from": names.get(r.from_id, "?")} for r in pending if r.to_id == player.id],
    }
    table = logic.table_of(db, player.id)
    if table is not None:
        ids = table.player_ids
        state["table"] = {"id": table.id, "index": table.index, "room": table.room,
                          "members": [names.get(pid, "?") for pid in ids],
                          "played": sum(1 for g in table.games if g.status == "revealed")}
        game = logic.current_game(db, table)
        if game is not None:
            state["game"] = _game_view(game, player, names)
            if len(ids) > 2:
                host, contestant = logic.roles_for(game.index + 1, ids)
                state["table"]["next"] = {"host": names.get(host, "?"), "contestant": names.get(contestant, "?")}
    if session.status == "ended":
        state["summary"] = logic.player_summary(db, session, player)
    return state


@router.get("/s/{session_id}/state")
def full_monty_public_state(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter_by(id=session_id, kind=KIND).first()
    if session is None:
        return JSONResponse({"error": "not_found"}, status_code=404, headers=NO_STORE)
    player = current_player(request, session_id, db)
    return JSONResponse(_public_state(db, session, player), headers=NO_STORE)


async def _json_body(request: Request) -> dict | None:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else None
    except Exception:
        return None


def _student(request: Request, session_id: str, db: DBSession):
    session = db.query(Session).filter_by(id=session_id, kind=KIND).first()
    player = current_player(request, session_id, db) if session else None
    if session is None or player is None:
        return None, None, JSONResponse({"error": "Join the show first."}, status_code=403, headers=NO_STORE)
    return session, player, None


@router.post("/s/{session_id}/vote")
async def full_monty_vote(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    session, player, denied = _student(request, session_id, db)
    if denied:
        return denied
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"error": "Send JSON like {\"phase\": \"before\", \"choice\": \"switch\"}."},
                            status_code=400, headers=NO_STORE)
    try:
        vote = logic.cast_vote(db, session, player, str(body.get("phase", "")), str(body.get("choice", "")))
    except logic.Refused as exc:
        return JSONResponse({"error": str(exc)}, status_code=409, headers=NO_STORE)
    return JSONResponse({"ok": True, "phase": vote.phase, "choice": vote.choice}, headers=NO_STORE)


@router.post("/s/{session_id}/seating")
async def full_monty_seating(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """Forming tables: ask someone to sit together, answer a request, take it back, or stand up."""
    session, player, denied = _student(request, session_id, db)
    if denied:
        return denied
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"error": "Send JSON like {\"action\": \"ask\", \"player\": \"...\"}."},
                            status_code=400, headers=NO_STORE)
    action = str(body.get("action", ""))
    ecosystem.lock_profiles(db)   # two answers at once must not overfill a table
    try:
        if action == "ask":
            logic.ask_to_sit(db, session, player, str(body.get("player", "")))
        elif action == "cancel":
            logic.cancel_ask(db, session, player)
        elif action in ("accept", "decline"):
            logic.answer(db, session, player, str(body.get("request", "")), action == "accept")
        elif action == "leave":
            logic.leave_table(db, session, player)
        else:
            return JSONResponse({"error": "Unknown action."}, status_code=400, headers=NO_STORE)
    except logic.Refused as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=409, headers=NO_STORE)
    except IntegrityError:
        db.rollback()   # the same seat was taken by a request answered at the same moment
        return JSONResponse({"error": "That seat was just taken."}, status_code=409, headers=NO_STORE)
    return JSONResponse(_public_state(db, session, player), headers=NO_STORE)


@router.post("/s/{session_id}/act")
async def full_monty_act(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """One move in the game at the student's table: hide, pick, open, decide or next."""
    session, player, denied = _student(request, session_id, db)
    if denied:
        return denied
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"error": "Send JSON like {\"action\": \"pick\", \"door\": 2}."},
                            status_code=400, headers=NO_STORE)
    if session.status == "ended":
        return JSONResponse({"error": "The show is over."}, status_code=409, headers=NO_STORE)
    table = logic.table_of(db, player.id)
    game = logic.current_game(db, table) if table else None
    if game is None:
        return JSONResponse({"error": "Your table isn't playing yet."}, status_code=409, headers=NO_STORE)
    action = str(body.get("action", ""))
    try:
        door = int(body.get("door", 0))
    except (TypeError, ValueError):
        door = 0
    # Serialize moves at a table so two partners tapping at once cannot both advance it.
    ecosystem.lock_profiles(db)
    db.refresh(game)
    try:
        if action == "hide":
            logic.hide_boat(db, game, player, door)
        elif action == "pick":
            logic.pick_door(db, game, player, door)
        elif action == "open":
            logic.open_door(db, game, player, door)
        elif action == "decide":
            logic.decide(db, game, player, str(body.get("decision", "")), _rule(session))
        elif action == "next":
            # A partner's tap may already have started the next game; a tap that names the old one is done.
            if str(body.get("game") or game.id) == game.id:
                logic.next_game(db, game, player)
        else:
            return JSONResponse({"error": "Unknown action."}, status_code=400, headers=NO_STORE)
    except logic.Refused as exc:
        db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=409, headers=NO_STORE)
    except IntegrityError:
        db.rollback()  # the partner's identical "next" already started the game
    return JSONResponse(_public_state(db, session, player), headers=NO_STORE)
