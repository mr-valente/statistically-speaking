"""Full Monty tables: the tables students form, the requests that form them, the games, and each
student's two beliefs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


GAME_STATUSES = ("hiding", "picking", "opening", "deciding", "revealed", "void")
REQUEST_STATUSES = ("pending", "accepted", "declined", "cancelled", "expired")
VOTE_PHASES = ("before", "after")
VOTE_CHOICES = ("switch", "stay", "same")
TABLE_SIZE = 3


class FullMontyTable(Base):
    """A table of two or three students. Seats are taken by invitation; the order of seats sets the rotation."""
    __tablename__ = "full_monty_tables"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False)                      # table number within the session
    created_at = Column(DateTime, default=_utcnow)

    __table_args__ = (UniqueConstraint("session_id", "index", name="uq_full_monty_table"),)

    seats = relationship("FullMontySeat", back_populates="table", cascade="all, delete-orphan",
                         order_by="FullMontySeat.position")
    games = relationship("FullMontyGame", back_populates="table", cascade="all, delete-orphan",
                         order_by="FullMontyGame.index")

    @property
    def player_ids(self) -> list[str]:
        return [s.player_id for s in self.seats]

    @property
    def room(self) -> bool:
        return len(self.seats) < TABLE_SIZE


class FullMontySeat(Base):
    __tablename__ = "full_monty_seats"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    table_id = Column(String, ForeignKey("full_monty_tables.id"), nullable=False, index=True)
    player_id = Column(String, ForeignKey("players.id"), nullable=False, unique=True)
    position = Column(Integer, nullable=False)                   # seat order at the table: the rotation
    created_at = Column(DateTime, default=_utcnow)

    table = relationship("FullMontyTable", back_populates="seats")


class FullMontyRequest(Base):
    """One student asking another to sit together. Accepting it seats them at one table."""
    __tablename__ = "full_monty_requests"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    from_id = Column(String, ForeignKey("players.id"), nullable=False, index=True)
    to_id = Column(String, ForeignKey("players.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=_utcnow)
    resolved_at = Column(DateTime, nullable=True)


class FullMontyGame(Base):
    __tablename__ = "full_monty_games"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    table_id = Column(String, ForeignKey("full_monty_tables.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False)                      # game number at this table
    host_id = Column(String, ForeignKey("players.id"), nullable=False)
    contestant_id = Column(String, ForeignKey("players.id"), nullable=False)
    status = Column(String, nullable=False, default="hiding")
    boat = Column(Integer, nullable=True)
    pick = Column(Integer, nullable=True)
    opened = Column(Integer, nullable=True)
    decision = Column(String, nullable=True)                     # "stay" / "switch"
    final = Column(Integer, nullable=True)
    won = Column(Boolean, nullable=True)
    rule = Column(String, nullable=True)                         # the house rule when the decision was made
    created_at = Column(DateTime, default=_utcnow)
    revealed_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("table_id", "index", name="uq_full_monty_game_index"),)

    table = relationship("FullMontyTable", back_populates="games")


class FullMontyVote(Base):
    """What a student believes about switching, asked before they play and again at the end."""
    __tablename__ = "full_monty_votes"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    player_id = Column(String, ForeignKey("players.id"), nullable=False, index=True)
    phase = Column(String, nullable=False)                       # "before" / "after"
    choice = Column(String, nullable=False)                      # "switch" / "stay" / "same"
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("player_id", "phase", name="uq_full_monty_vote"),)
