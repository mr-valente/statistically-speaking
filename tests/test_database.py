"""Startup against a database left by an earlier release."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import tests.support  # noqa: F401  (pins the in-process app's environment before app imports)
from sqlalchemy import create_engine, inspect

from app.database import init_db


FIRST_RELEASE = """
CREATE TABLE teachers (id VARCHAR PRIMARY KEY, name VARCHAR);
CREATE TABLE sessions (id VARCHAR PRIMARY KEY, teacher_id VARCHAR);
CREATE TABLE players (id VARCHAR PRIMARY KEY, session_id VARCHAR);
CREATE TABLE full_monty_pairs (id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, "index" INTEGER,
    first_id VARCHAR NOT NULL, second_id VARCHAR, retired BOOLEAN NOT NULL, created_at DATETIME);
CREATE INDEX ix_full_monty_pairs_session_id ON full_monty_pairs (session_id);
CREATE TABLE full_monty_games (id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, pair_id VARCHAR NOT NULL,
    "index" INTEGER, host_id VARCHAR, contestant_id VARCHAR NOT NULL, status VARCHAR NOT NULL, car INTEGER,
    pick INTEGER, opened INTEGER, decision VARCHAR, final INTEGER, won BOOLEAN, rule VARCHAR,
    created_at DATETIME, revealed_at DATETIME);
CREATE INDEX ix_full_monty_games_session_id ON full_monty_games (session_id);
CREATE INDEX ix_full_monty_games_pair_id ON full_monty_games (pair_id);
CREATE TABLE full_monty_votes (id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, player_id VARCHAR NOT NULL,
    phase VARCHAR NOT NULL, choice VARCHAR NOT NULL, created_at DATETIME, updated_at DATETIME);
INSERT INTO full_monty_pairs VALUES ('p1', 's1', 1, 'a', 'b', 0, NULL);
INSERT INTO full_monty_games VALUES ('g1', 's1', 'p1', 1, 'a', 'b', 'revealed', 2, 1, 3, 'switch', 2, 1, NULL, NULL, NULL);
INSERT INTO full_monty_votes VALUES ('v1', 's1', 'a', 'before', 'switch', NULL, NULL);
"""


class LegacySchema(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "app.db"
        with sqlite3.connect(self.path) as db:
            db.executescript(FIRST_RELEASE)
        self.engine = create_engine(f"sqlite:///{self.path}")

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def columns(self, table):
        return {c["name"] for c in inspect(self.engine).get_columns(table)}

    def test_pair_era_tables_are_moved_aside_and_rebuilt(self):
        init_db(self.engine)
        tables = set(inspect(self.engine).get_table_names())
        self.assertIn("table_id", self.columns("full_monty_games"))
        self.assertNotIn("pair_id", self.columns("full_monty_games"))
        self.assertTrue({"full_monty_tables", "full_monty_seats", "full_monty_requests"} <= tables)
        self.assertNotIn("full_monty_pairs", tables)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM full_monty_games").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT pair_id FROM legacy_full_monty_games").fetchall(), [("p1",)])
            self.assertEqual(db.execute("SELECT first_id FROM legacy_full_monty_pairs").fetchall(), [("a",)])
            # Votes kept their shape and stay where they are.
            self.assertEqual(db.execute("SELECT choice FROM full_monty_votes").fetchall(), [("switch",)])

    def test_startup_is_repeatable(self):
        init_db(self.engine)
        init_db(self.engine)
        tables = set(inspect(self.engine).get_table_names())
        self.assertEqual({t for t in tables if t.startswith("legacy_")},
                         {"legacy_full_monty_pairs", "legacy_full_monty_games"})
        self.assertIn("table_id", self.columns("full_monty_games"))
