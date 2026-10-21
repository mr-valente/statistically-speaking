"""Application configuration from environment variables and defaults."""

import os
import re
import secrets
from pathlib import Path


PRODUCTION = os.environ.get("APP_ENV", "development") == "production"
ROOT_PATH = os.environ.get("ROOT_PATH", "").rstrip("/")
if ROOT_PATH and not re.fullmatch(r"(?:/[a-z0-9][a-z0-9-]*)+", ROOT_PATH):
    raise RuntimeError("ROOT_PATH must be empty or a lowercase URL path")

_secret_file = os.environ.get("SESSION_SECRET_FILE")
if _secret_file and os.environ.get("SESSION_SECRET"):
    raise RuntimeError("Set only one of SESSION_SECRET and SESSION_SECRET_FILE")
SESSION_SECRET = (Path(_secret_file).read_text().strip() if _secret_file
                  else os.environ.get("SESSION_SECRET", ""))
if PRODUCTION and (len(SESSION_SECRET) < 32 or SESSION_SECRET in {"change-me-too", "local"}):
    raise RuntimeError("Production requires a persistent SESSION_SECRET of at least 32 characters")
SESSION_SECRET = SESSION_SECRET or secrets.token_hex(32)
SESSION_COOKIE = "statistically_speaking_session"
DB_PATH = Path(os.environ.get("DB_PATH", "/data/app.db"))
if not DB_PATH.is_absolute():
    raise RuntimeError("DB_PATH must be absolute")
PORT: int = int(os.environ.get("PORT", "8000"))

# How many joined classrooms one browser remembers for rejoin.
REMEMBERED_PLAYERS: int = 12
