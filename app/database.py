"""Database engine and session setup for SQLite via SQLAlchemy."""

import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DB_PATH, PRODUCTION

if not DB_PATH.parent.is_dir():
    if PRODUCTION:
        raise RuntimeError("Database directory is missing; mount the application's data directory")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Experience modules must be imported first so their models register."""
    import app.experiences  # noqa: F401  (registers experience models on Base)
    Base.metadata.create_all(bind=engine)


def database_ready() -> bool:
    """Read-only probe: never create a replacement database or change classroom state."""
    try:
        with sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=1) as db:
            db.execute("SELECT id FROM teachers LIMIT 1").fetchone()
            db.execute("SELECT id FROM sessions LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
