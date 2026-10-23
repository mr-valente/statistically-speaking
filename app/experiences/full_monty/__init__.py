"""Full Monty: partners play the Monty Hall game; the class's record settles the switch question."""

from app.experiences.full_monty import models  # noqa: F401  (register tables)
from app.experiences.full_monty.routes import router


def _descriptor():
    from app.experiences import Experience
    return Experience(
        kind="full_monty",
        slug="full-monty",
        name="Full Monty",
        glyph="🚪",
        question="Three doors. Two goats. One boat. Do you switch?",
        description=("Grab a partner or two and take turns as host and contestant. Hide the boat, open a goat, "
                     "stay or switch. Every game lands in the class record."),
        router=router,
        new_session_route="full_monty_new",
        teacher_route="full_monty_teacher",
        student_route="full_monty_student",
        solo_route="full_monty_solo",
        solo_label="Play solo vs. Monty",
    )


EXPERIENCE = _descriptor()
