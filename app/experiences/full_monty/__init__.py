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
        question="Three doors. One car. Should you switch?",
        description=("Students pair up and take turns as host and contestant. The host hides the car and "
                     "opens a goat door; the contestant stays or switches. Every game lands in the class record, "
                     "and the record answers the question."),
        router=router,
        new_session_route="full_monty_new",
        teacher_route="full_monty_teacher",
        student_route="full_monty_student",
    )


EXPERIENCE = _descriptor()
