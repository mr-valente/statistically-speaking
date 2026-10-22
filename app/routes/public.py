"""Public routes: landing page, joining a session, and the student entry point."""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session as DBSession

from app import qr, ecosystem
from app.database import get_db
from app.experiences import EXPERIENCES, get_experience
from app.identity import current_player, join_as_player
from app.models import Session
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html",
                                      context={"request": request, "experiences": list(EXPERIENCES.values())})


def solo_experiences():
    """Experiences that can be played alone, offered on the join page to anyone without a code."""
    return [e for e in EXPERIENCES.values() if e.solo_route]


@router.get("/join", response_class=HTMLResponse)
def join_form(request: Request, code: str = ""):
    if redirect := ecosystem.login_required(request):
        return redirect
    return templates.TemplateResponse(request=request, name="join.html",
                                      context={"request": request, "error": None, "code": code.upper()[:6],
                                               "solo": solo_experiences()})


def join_url(request: Request, code: str) -> str:
    """The absolute join link for a code, with the code pre-filled: what the QR encodes."""
    return str(request.url_for("join_form").include_query_params(code=code))


@router.get("/join/qr/{code}.svg")
def join_qr(code: str, request: Request, db: DBSession = Depends(get_db)):
    """A scannable QR for a live session's join link. Codes are public, so no login is needed."""
    code = code.strip().upper()
    session = db.query(Session).filter_by(join_code=code).first()
    if session is None or session.status == "ended":
        return Response(status_code=404)
    return Response(qr.svg_document(join_url(request, code)), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})


def _join_error(request: Request, message: str, code: str, status_code: int):
    return templates.TemplateResponse(request=request, name="join.html",
                                      context={"request": request, "error": message, "code": code,
                                               "solo": solo_experiences()},
                                      status_code=status_code)


@router.post("/session/join")
def join_session(
    request: Request,
    join_code: str = Form(...),
    player_name: str = Form(''),
    db: DBSession = Depends(get_db),
):
    join_code = join_code.strip().upper()
    join_target = request.url_for('join_form').include_query_params(code=join_code)
    if redirect := ecosystem.login_required(request, join_target.path + '?' + join_target.query):
        return redirect
    player_name = ecosystem.display_name(request, " ".join(player_name.split())[:60])

    if not player_name:
        return _join_error(request, "Please enter your name.", join_code, 400)

    session = db.query(Session).filter_by(join_code=join_code).first()
    if session is None:
        return _join_error(request, f"No session found with code '{join_code}'.", join_code, 404)
    if session.status == "ended":
        return _join_error(request, "This session has already ended.", join_code, 400)

    player = join_as_player(request, db, session, player_name)
    if player is None:
        return _join_error(request, "That name is already taken in this session. Try adding an initial.",
                           join_code, 400)

    return RedirectResponse(url=request.url_for("student_entry", session_id=session.id), status_code=303)


@router.get("/s/{session_id}")
def student_entry(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """Dispatch a joined student to the experience that owns this session."""
    session = db.query(Session).filter_by(id=session_id).first()
    experience = get_experience(session.kind) if session else None
    if session is None or experience is None or current_player(request, session_id, db) is None:
        return RedirectResponse(url=request.url_for("join_form"), status_code=303)
    return RedirectResponse(url=request.url_for(experience.student_route, session_id=session_id), status_code=303)
