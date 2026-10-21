"""Private container CLI and request gate for safe classroom update deferral.

Mirrors the Quacktuaries contract so an Athenaeum host can ask whether a class
is in progress before replacing the container.
"""
import asyncio
from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from app.config import DB_PATH

# Per-database names isolate local test servers; /tmp is container-local tmpfs.
NAME = hashlib.sha256(str(DB_PATH).encode()).hexdigest()[:16]
LOCK = Path('/tmp') / ('statistically-speaking-requests-' + NAME + '.lock')
HOLD = LOCK.with_suffix('.hold')


def activity():
    with closing(sqlite3.connect(DB_PATH.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
        # A lobby is protected too.
        active = db.execute("SELECT 1 FROM sessions WHERE status != 'ended' LIMIT 1").fetchone() is not None
        schema = db.execute('PRAGMA user_version').fetchone()[0]
    return {'protocol': 1, 'active_class': active, 'data_schema': schema, 'held': HOLD.exists()}


def operation(command):
    if command not in ('status', 'drain', 'release'):
        raise ValueError('Unknown operation')
    with open(LOCK, 'a') as lock:
        deadline = time.monotonic() + 25
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Requests did not drain')
                time.sleep(0.05)
        if command == 'release':
            HOLD.unlink(missing_ok=True)
        state = activity()
        if command == 'drain' and not state['active_class']:
            HOLD.touch(mode=0o600, exist_ok=True)
            state['held'] = True
        return state


class UpdateGate:
    """Serialize the host's drain decision with complete HTTP requests."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        with open(LOCK, 'a') as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.02)
            if HOLD.exists() and not scope['path'].endswith('/_health'):
                from starlette.responses import PlainTextResponse
                return await PlainTextResponse('Brief maintenance. Please retry shortly.', status_code=503,
                    headers={'Retry-After': '30', 'Cache-Control': 'no-store'})(scope, receive, send)
            await self.app(scope, receive, send)


if __name__ == '__main__':
    try:
        print(json.dumps(operation(sys.argv[1]), sort_keys=True))
    except Exception:
        print('Statistically Speaking operations unavailable; update must be deferred.', file=sys.stderr)
        sys.exit(1)
