"""Experience registry.

Each experience is a package exposing an ``EXPERIENCE`` descriptor. Sessions
store the experience ``kind`` so the generic ``/s/{id}`` and ``/admin/s/{id}``
entry points can dispatch to the right views. Importing this module imports
every experience, which also registers their ORM models on the shared Base.
"""

from dataclasses import dataclass

from fastapi import APIRouter


@dataclass(frozen=True)
class Experience:
    kind: str            # stored on Session.kind, e.g. "full_monty"
    slug: str            # URL segment under /x/, e.g. "full-monty"
    name: str            # display name
    glyph: str           # one emoji for the landing card
    question: str        # the question the experience asks, one line
    description: str     # a sentence or two for the landing card
    router: APIRouter
    new_session_route: str   # url_for name: teacher creates a session
    teacher_route: str       # url_for name(session_id=...): teacher's session dashboard
    student_route: str       # url_for name(session_id=...): student's view
    solo_route: str | None = None   # url_for name: play alone against the computer, no session needed


from app.experiences.full_monty import EXPERIENCE as _full_monty  # noqa: E402

EXPERIENCES: dict[str, Experience] = {e.kind: e for e in (_full_monty,)}


def get_experience(kind: str) -> Experience | None:
    return EXPERIENCES.get(kind)
