"""Teacher routes shared by every experience: login, session list, dispatch."""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DBSession

from app import ecosystem
from app.database import get_db
from app.experiences import EXPERIENCES, get_experience
from app.identity import current_teacher, login_teacher, owns_session
from app.models import Session
from app.templating import templates

router = APIRouter(prefix="/admin")


# ── Login ──────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_login_page(request: Request, db: DBSession = Depends(get_db)):
    if redirect := ecosystem.login_required(request):
        return redirect
    if ecosystem.account(request):
        login_teacher(request, db, ecosystem.display_name(request))
        return RedirectResponse(url=request.url_for('admin_dashboard'), status_code=303)
    if current_teacher(request, db):
        return RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)
    return templates.TemplateResponse(request=request, name="admin_login.html",
                                      context={"request": request, "error": None})


@router.post("/login")
def admin_login(request: Request, teacher_name: str = Form(''), db: DBSession = Depends(get_db)):
    if redirect := ecosystem.login_required(request, request.url_for('admin_login_page').path):
        return redirect
    teacher_name = ecosystem.display_name(request, " ".join(teacher_name.split())[:60])
    error = None
    if not teacher_name:
        error = "Please enter your name."
    if error:
        return templates.TemplateResponse(request=request, name="admin_login.html",
                                          context={"request": request, "error": error}, status_code=400)
    login_teacher(request, db, teacher_name)
    return RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)


@router.get("/logout")
def admin_logout(request: Request):
    if ecosystem.account(request):
        return RedirectResponse("/account/", status_code=303)
    request.session.pop("teacher_id", None)
    return RedirectResponse(url=request.url_for("home"), status_code=303)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: DBSession = Depends(get_db)):
    teacher = current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url=request.url_for("admin_login_page"), status_code=303)
    sessions = (db.query(Session).filter(Session.teacher_id.in_(getattr(teacher, "ecosystem_teacher_ids", [teacher.id])))
                .order_by(Session.created_at.desc()).all())
    return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={
        "request": request, "teacher": teacher, "sessions": sessions, "experiences": EXPERIENCES,
    })


@router.get("/sessions/new", response_class=HTMLResponse)
def new_session_form(request: Request, db: DBSession = Depends(get_db)):
    """Pick an experience; each experience owns its own creation form."""
    teacher = current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url=request.url_for("admin_login_page"), status_code=303)
    return templates.TemplateResponse(request=request, name="admin_new_session.html", context={
        "request": request, "teacher": teacher, "experiences": list(EXPERIENCES.values()),
    })


@router.get("/s/{session_id}")
def admin_session_entry(session_id: str, request: Request, db: DBSession = Depends(get_db)):
    """Dispatch a teacher to the experience that owns this session."""
    teacher = current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url=request.url_for("admin_login_page"), status_code=303)
    session = db.query(Session).filter_by(id=session_id).first()
    experience = get_experience(session.kind) if session else None
    if not owns_session(teacher, session) or experience is None:
        return RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)
    return RedirectResponse(url=request.url_for(experience.teacher_route, session_id=session_id), status_code=303)
