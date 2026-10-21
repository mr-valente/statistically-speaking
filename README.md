# 🎙 Statistically Speaking

A self-hosted, single-container suite of game-show rounds for teaching statistics. Teachers run a session from a laptop, put a presenter view on the projector, and students join on their phones with a six-letter code. Each experience is a small, self-contained lesson.

Built with **Python/FastAPI**, **Jinja2** server-rendered templates, vanilla JS, and **SQLite**: the same stack and deployment contract as [Bernoulli](../bernoulli), whose suite/experience structure this repeats.

## Experiences

### Full Monty — *Three doors. One car. Should you switch?*

The Monty Hall problem, played by partners and settled by the class record.

- **Join and answer.** Students join with the code and answer one question while they wait: when the host opens a goat door and offers the switch, is it better to switch, stay, or does it make no difference? The projector shows how many have answered, not the split.
- **Seat.** The teacher seats everyone. Students are paired at numbered tables; an odd student out plays against the House, which hosts. Late arrivals wait in a list until the teacher seats newcomers; a reshuffle reseats the whole room.
- **Play.** Partners take turns. The **host** hides the car (taps a door), sees the contestant's pick, and must open a door that hides a goat: the app only accepts a legal door and says why when it refuses. The **contestant** picks a door, then stays or switches. The doors open, both phones show the result, and either partner starts the next game with the roles swapped.
- **Rule.** The teacher can let contestants choose, or make everyone stay or everyone switch for a while, so both columns of the record fill up.
- **The record.** The projector and the teacher's dashboard show the win rate for staying and for switching, the share of first picks that were right, and a chart of both rates after each game with 1/3, 1/2 and 2/3 marked. A plain-English line says how often a coin flip would do at least as well as switching did.
- **The end.** Students answer the question again, then see their own games and the class record. The projector shows the record and the room's beliefs before and after. Games and beliefs export as CSV.

A design note with the reasoning and the ideas not built is in [docs/full-monty.md](docs/full-monty.md).

## Quick Start (Local Development)

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.lock
export SESSION_SECRET="dev-only-secret"
export DB_PATH="$PWD/dev.db"
.venv/bin/python -m app
# open http://localhost:8000
```

Tests run a real server against disposable databases:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Quick Start (Docker)

```bash
export SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
docker compose up -d --build
open http://localhost:8000
```

## Running a class

1. Go to `/admin`, enter your name, and create a **Full Monty** session. Share the join code.
2. Open the **Presenter view** in a new window and put it on the projector. It shows the join URL, the code and a QR code, then the record.
3. Students scan the QR code or go to `/join` on their phones and answer the first question. (**Join with QR** on the teacher page shows the same QR full-size if there is no projector.)
4. **Seat everyone.** Each table's phones take it from there. Seat newcomers as they arrive.
5. Watch the record fill. Switch the **rule** when one column is short. Reshuffle tables if a pair goes quiet.
6. **End session** when you are done: students answer the question again and get their summaries; the projector shows the answer.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SESSION_SECRET` | random in development | Stable signing key; required in production unless supplied by file |
| `SESSION_SECRET_FILE` | unset | Read the signing secret from a protected file; exclusive with `SESSION_SECRET` |
| `DB_PATH` | `/data/app.db` | Absolute path to the SQLite database |
| `PORT` | `8000` | Server port when started with `python -m app` |
| `ROOT_PATH` | empty | Public prefix, e.g. `/statistically-speaking`; the proxy strips it upstream |
| `APP_ENV` | `development` | `production` requires a strong stable secret and Secure cookies |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Trusted proxy IPs |
| `ACCOUNT_SERVICE_URL`, `ATHENAEUM_APP_ID` | unset | Shared Athenaeum accounts; see `docs/deployment.md` |

## Project Structure

```
statistically-speaking/
├── app/
│   ├── config.py            # Environment variables & defaults
│   ├── database.py          # SQLAlchemy engine, session, health probe
│   ├── models.py            # Shared ORM: teachers, sessions, players
│   ├── identity.py          # Account or rejoin-token identity for teachers and students
│   ├── ecosystem.py         # Pinned Athenaeum account adapter
│   ├── performance.py       # Finalized games for the shared history
│   ├── operations.py        # Update-deferral gate and private CLI (Athenaeum plumbing)
│   ├── qr.py                # Join-link QR codes as SVG (segno)
│   ├── main.py              # FastAPI app; mounts every registered experience under /x/<slug>
│   ├── routes/
│   │   ├── public.py        # Landing, join, join QR, student dispatch (/s/{id})
│   │   └── admin.py         # Teacher login, session list, teacher dispatch (/admin/s/{id})
│   ├── experiences/
│   │   ├── __init__.py      # Experience registry
│   │   └── full_monty/
│   │       ├── models.py    # full_monty_pairs, full_monty_games, full_monty_votes
│   │       ├── logic.py     # Doors, tables, the record, plain-English numbers
│   │       └── routes.py    # Teacher controls, presenter, student play, JSON state, CSV
│   ├── templates/           # Jinja2 (shared pages + full_monty/)
│   └── static/              # show.css, show.js, one script per page, pinned design assets
├── docs/deployment.md       # Athenaeum contract
├── docs/full-monty.md       # Design note and lesson outline
├── tests/                   # Logic, real-server deployment, hosted identity
├── Dockerfile               # runtime → standalone / athenaeum targets
└── docker-compose.yml       # Standalone local development
```

### Adding an experience

Create `app/experiences/<name>/` with `models.py`, `logic.py`, `routes.py`, and an `__init__.py` exposing `EXPERIENCE = Experience(...)` (kind, slug, name, glyph, question, description, router, and the three route names for creating a session, the teacher view, and the student view). Register it in `app/experiences/__init__.py`. The landing page, the teacher's session list, and the `/s/{id}` / `/admin/s/{id}` dispatchers pick it up automatically.

## License

MIT. The bundled CaskaydiaCove subset keeps its own license in `app/static/design/fonts/`.
