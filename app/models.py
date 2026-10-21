"""Core ORM models shared by every experience: teachers, sessions, players.

Experience-specific tables live beside their experience in ``app/experiences/``.
The shared account adapter expects exactly these three names and columns.
"""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    rejoin_token = Column(String(32), nullable=False)  # secret token for reconnecting
    created_at = Column(DateTime, default=_utcnow)

    sessions = relationship("Session", back_populates="teacher", cascade="all, delete-orphan")


class Session(Base):
    """One classroom run of one experience."""
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=_uuid)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=False)
    kind = Column(String, nullable=False, index=True)  # experience kind, e.g. "full_monty"
    join_code = Column(String(6), unique=True, nullable=False, index=True)
    status = Column(String, nullable=False, default="lobby")  # lobby / active / ended
    settings_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=_utcnow)
    ended_at = Column(DateTime, nullable=True)

    teacher = relationship("Teacher", back_populates="sessions")
    players = relationship("Player", back_populates="session", cascade="all, delete-orphan")

    @property
    def settings(self) -> dict:
        return json.loads(self.settings_json or "{}")

    def update_settings(self, **changes) -> None:
        self.settings_json = json.dumps({**self.settings, **changes})


class Player(Base):
    __tablename__ = "players"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    name = Column(String, nullable=False)
    rejoin_token = Column(String(32), nullable=False)  # secret token for reconnecting
    created_at = Column(DateTime, default=_utcnow)

    session = relationship("Session", back_populates="players")
