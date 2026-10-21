# Athenaeum deployment contract

Service: `statistically-speaking`. Public path: `/statistically-speaking/`. Internal port: `8000`. One application process and one SQLite database. Hosted deployments may sleep when idle; shared-account synchronization runs while awake. Every live view polls a JSON state endpoint (students and the projector every 1.5 s, the teacher every 2 s), so a classroom of 30 produces roughly 20 small requests per second while a session is running. A student's move answers with the same state document, so a tap costs one request.

This contract mirrors Bernoulli so the same Caddy, Compose, backup, and update recipes apply. The service name carries a hyphen; Athenaeum's host tooling derives environment variable names from it with underscores (`STATISTICALLY_SPEAKING_IMAGE`, `STATISTICALLY_SPEAKING_SECRET_FILE`) and everything else (Compose service, secret `statistically-speaking_session`, data directory, Sablier group) from the name as written.

## Runtime

Use `python -m app` for the container entry point. It supplies `ROOT_PATH` to Uvicorn as well as FastAPI, so mounted static files receive the correct ASGI path. Templates, redirects, and the polling URLs embedded in pages all use named routing helpers. Caddy strips `/statistically-speaking` upstream. Empty `ROOT_PATH` supports standalone deployment. `DB_PATH` is authoritative.

Production configuration:

```text
APP_ENV=production
ROOT_PATH=/statistically-speaking
PORT=8000
DB_PATH=/data/app.db
SESSION_SECRET_FILE=/run/secrets/statistically-speaking_session
FORWARDED_ALLOW_IPS=*
```

Use a protected secret file containing a random key of at least 32 characters. Alternatively set `SESSION_SECRET`, but never both. Missing/short production keys fail startup. The image has no embedded development key. Preserve the secret across replacement: changing it invalidates existing sessions and browser rejoin ownership for teachers and students alike.

The cookie is `statistically_speaking_session`, scoped to the configured prefix (or `/` standalone), host-only, HttpOnly, SameSite=Lax, and Secure in production. It carries the teacher id plus a small map of the classrooms this browser has joined (capped at twelve seats). Athenaeum trusts proxy headers on its private apps network; that wildcard is supplied by Athenaeum's Compose file, not embedded in the image. Standalone deployments should allow only their own trusted proxies. Do not publish application ports in production.

The image runs as UID/GID `10001:10001`, supports a read-only root filesystem, and writes only to `/data` and temporary scratch space. Every response carries a Content-Security-Policy that allows only the app's own scripts and stylesheets; pages contain no inline script or style. `PORT` is honored by the entry point; the image healthcheck targets the ecosystem's fixed port 8000.

Awake memory is about 70 MiB on the workstation's `docker stats` after a full test session, which places the app in the `light` session tier; measure again on the host after the first deployment.

## Data and health

Mount `/srv/athenaeum/apps/statistically-speaking/data/` at `/data`, owned by the runtime UID/GID. Production startup refuses to create a missing parent directory. An explicitly prepared empty directory initializes the schema (`teachers`, `sessions`, `players`, plus one table set per experience, currently `full_monty_pairs`, `full_monty_games` and `full_monty_votes`, and the additive `ecosystem_links` and `ecosystem_outbox`). There are no startup migrations yet.

`GET /_health` returns 200 with `{"status":"ok"}` only if a read-only SQLite connection can read the `teachers` and `sessions` tables; otherwise 503 with a generic status. It never creates a database or advances a class.

The optional private CLI `python -m app.operations status|drain|release` reports whether any session is not yet ended and can hold new requests behind a 503 while the host replaces the container. The `UpdateGate` middleware serialises that decision with in-flight requests exactly as Bernoulli does.

Consistent backups must use SQLite's supported backup API and preserve the signing key in encrypted recovery material. Do not copy the live database file periodically; CSV exports do not restore ownership or complete session state.

## Builds and verification

`requirements.txt` records allowed dependency ranges; `requirements.lock` pins the resolved runtime set, including transitives, the same versions as Bernoulli. Docker installs the lock with binary wheels only. The Python base is pinned to the same multi-platform digest as the other apps.

```bash
docker build -t statistically-speaking:local .
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  -v "$PWD/tests:/app/tests:ro" statistically-speaking:local \
  python -m unittest discover -s tests -v
```

The tests cover the door rules and the plain-English numbers, and launch a real Uvicorn against disposable databases under the `/statistically-speaking` prefix to check routing, the cookie contract, ownership, information gating (the car stays the host's secret until the reveal; the projector sees nothing personal), seating and reshuffling, the rule, the House, persistence across restart, the exports, and hosted identity against a stand-in account service, including the finalized results it publishes.

Shared-style version: 0.2.0 (After hours). Pinned copies of `tokens.css`, `base.css` and the fonts are in `app/static/design/`.

## Manual image delivery

Add an independent `statistically-speaking` entry with its own SemVer counter to `~/.config/builder/builds.yaml`, then from a normal local Fish shell:

```fish
build --dry-run --version v0.1.0 statistically-speaking
build --version v0.1.0 statistically-speaking
build statistically-speaking   # later releases increment only this app's version
```

| Variant | Moving tag | Retained version example | Defaults |
| --- | --- | --- | --- |
| Standalone | `valentemath/statistically-speaking:latest` | `valentemath/statistically-speaking:v0.1.0` | Root path, development mode |
| Athenaeum | `valentemath/statistically-speaking:latest-athenaeum` | `valentemath/statistically-speaking:v0.1.0-athenaeum` | `/statistically-speaking`, production mode |

Release `docker/compose.yaml` builds ARM64 for Oracle; set `STATISTICALLY_SPEAKING_PLATFORM=linux/amd64` only when publishing for an AMD64 host. The hosted variant requires a session secret at runtime. Neither recipe depends on an Athenaeum checkout. A plain `docker build .` selects the standalone target; `docker-compose.yml` remains for local development.

## Athenaeum integration

Athenaeum registers the app beside Bernoulli: `content/statistics/statistically-speaking.md` is the project card, `deploy/caddy/routes.caddy` carries the `/statistically-speaking` slash redirect and prefixed route (the `/_health` probe stays internal), `compose.yaml` runs `valentemath/statistically-speaking:latest-athenaeum` with the `/srv/athenaeum/apps/statistically-speaking/data` mount and the `/etc/athenaeum/statistically-speaking-session-secret` Compose secret, and the host tools' `APPS` registry (`ops/athenaeum_ops/common.py`) covers preflight, hourly snapshots, isolated restore tests and HTTPS verification. Override the image with `STATISTICALLY_SPEAKING_IMAGE` in `/etc/athenaeum/compose.env`. Schedule updates outside active classes.

## Shared Athenaeum accounts

The hosted stack supplies `ACCOUNT_SERVICE_URL=http://accounts:8000` and `ATHENAEUM_APP_ID=statistically-speaking`. The adapter derives its private API credential from the existing per-app session key; never expose that credential to the browser. A standalone image omits these settings and keeps the name-and-join-code flow.

On startup, SQLAlchemy creates the additive `ecosystem_links` and `ecosystem_outbox` tables alongside the classroom tables. Google-linked players and teachers recover their seats from the shared account on another browser, including a game in progress. Saving original guest activity requires an explicit action from a browser with its rejoin token. Names never establish ownership.

Hosted Join and Teacher Login first send anonymous users to the shared sign-in page, preserving the return path and join code. Google and named guest identities skip further name forms; teachers go directly to their dashboard. The landing page stays public.

Performance: one record per revealed Full Monty game for a Google-linked contestant (`source_id` `full-monty:<game id>`, activity `full_monty`) with the decision, whether it won, and whether the first pick was right, plus the classroom, table, game number, the rule in force and whether the House hosted. Hosting a game, beliefs and guests' games are not published. The outbox is written in the classroom transaction; a background worker retries every 15 seconds while awake and reconciles finalized records on startup.

The pinned adapter lives in `app/ecosystem.py`; its source and integration contract are in the Athenaeum repository under `accounts/client/` and `docs/reference/accounts.md`. Update the copies together.
