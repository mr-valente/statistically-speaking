"""Full Monty tables: tables of partners, the games they play, and each student's two beliefs."""

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
VOTE_PHASES = ("before", "after")
VOTE_CHOICES = ("switch", "stay", "same")


class FullMontyPair(Base):
    """Two partners at one table. A table with no second player is hosted by the House (the server)."""
    __tablename__ = "full_monty_pairs"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False)                      # table number within the session
    first_id = Column(String, ForeignKey("players.id"), nullable=False)   # hosts the odd games
    second_id = Column(String, ForeignKey("players.id"), nullable=True)   # hosts the even games; None = the House
    retired = Column(Boolean, nullable=False, default=False)     # replaced by a reshuffle
    created_at = Column(DateTime, default=_utcnow)

    __table_args__ = (UniqueConstraint("session_id", "index", name="uq_full_monty_table"),)

    games = relationship("FullMontyGame", back_populates="pair", cascade="all, delete-orphan",
                         order_by="FullMontyGame.index")

    @property
    def house(self) -> bool:
        return self.second_id is None


class FullMontyGame(Base):
    __tablename__ = "full_monty_games"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    pair_id = Column(String, ForeignKey("full_monty_pairs.id"), nullable=False, index=True)
    index = Column(Integer, nullable=False)                      # game number at this table
    host_id = Column(String, ForeignKey("players.id"), nullable=True)   # None = the House
    contestant_id = Column(String, ForeignKey("players.id"), nullable=False)
    status = Column(String, nullable=False, default="hiding")
    car = Column(Integer, nullable=True)
    pick = Column(Integer, nullable=True)
    opened = Column(Integer, nullable=True)
    decision = Column(String, nullable=True)                     # "stay" / "switch"
    final = Column(Integer, nullable=True)
    won = Column(Boolean, nullable=True)
    rule = Column(String, nullable=True)                         # the show's rule when the decision was made
    created_at = Column(DateTime, default=_utcnow)
    revealed_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("pair_id", "index", name="uq_full_monty_game_index"),)

    pair = relationship("FullMontyPair", back_populates="games")

    @property
    def house(self) -> bool:
        return self.host_id is None


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
