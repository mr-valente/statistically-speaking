"""Database engine and session setup for SQLite via SQLAlchemy."""

import sqlite3
from sqlalchemy import create_engine, inspect, text
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


# Tables whose shape changed since a release, keyed by a column the current schema requires.
# create_all never alters an existing table, so a table missing its column is moved aside
# together with the tables listed with it, and a fresh one is built. The old rows stay in
# the database under a legacy_ name.
LEGACY_SHAPES = {
    "full_monty_games": ("table_id", ("full_monty_pairs",)),   # first release stored partners as pairs
}


def retire_legacy_tables(connection) -> list[str]:
    """Rename out-of-date tables (and their indexes) so create_all can rebuild them. Returns the names moved."""
    inspector = inspect(connection)
    present = set(inspector.get_table_names())
    moved = []
    for table, (column, companions) in LEGACY_SHAPES.items():
        if table not in present:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        for name in (table, *companions):
            if name not in present:
                continue
            for index in inspector.get_indexes(name):
                connection.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
            target, n = f"legacy_{name}", 1
            while target in present:
                n += 1
                target = f"legacy_{name}_{n}"
            connection.execute(text(f'ALTER TABLE "{name}" RENAME TO "{target}"'))
            present.add(target)
            moved.append(name)
    return moved


def init_db(bind=None):
    """Move aside any out-of-date tables, then create what is missing. Experience modules must be
    imported first so their models register."""
    import app.experiences  # noqa: F401  (registers experience models on Base)
    with (bind or engine).begin() as connection:
        retire_legacy_tables(connection)
        Base.metadata.create_all(bind=connection)


def database_ready() -> bool:
    """Read-only probe: never create a replacement database or change classroom state."""
    try:
        with sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=1) as db:
            db.execute("SELECT id FROM teachers LIMIT 1").fetchone()
            db.execute("SELECT id FROM sessions LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
