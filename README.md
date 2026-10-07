🇬🇧 English | [🇹🇷 Türkçe](README.tr.md)

# Rapid Quiz — Backend API

A REST API for a fast-paced trivia game: **20 questions, 5 seconds each, no sign-up**, and a **Top 10 leaderboard per category**. Scoring, timing and answer checking all happen on the server.

> **Part of Rapid Quiz**
>
> | Repository | Role |
> | --- | --- |
> | [RapidQuizBackend](https://github.com/busracankit/RapidQuizBackend) | Django REST API: game logic, scoring, leaderboards (this repo) |
> | [RapidQuizFrontend](https://github.com/busracankit/RapidQuizFrontend) | Web client (Vue 3 + TypeScript) |
> | [RapidQuizAndroid](https://github.com/busracankit/RapidQuizAndroid) | Android client (Kotlin + Jetpack Compose) |
>
> There is no live deployment. The app was deployed once to DigitalOcean App Platform for testing and then shut down. Everything runs locally with the steps below.

## Features

- 5 categories with 300 questions (60 each: 24 easy, 24 medium, 12 hard). Each game draws 20 random questions (8 easy, 8 medium, 4 hard) and shuffles the answer choices.
- A 5-second limit per question, enforced by the server. Faster correct answers earn more points (100–150 per question).
- Anonymous play: a player only types a name at the end to save their score.
- A Top 10 leaderboard per category, with the player's rank even when they don't make the top 10.
- Name validation with a profanity filter.
- Django admin for managing categories, questions and leaderboard entries.
- An OpenAPI 3 schema with Swagger UI, one shared contract for the web and mobile clients.

## Tech stack

| Area | Tools |
| --- | --- |
| Language & framework | Python 3.14, Django 6.1, Django REST Framework 3.18 |
| Database | PostgreSQL 18 (psycopg 3) |
| API docs | drf-spectacular (OpenAPI 3 + Swagger UI, served locally via sidecar) |
| Config & serving | django-environ, django-cors-headers, gunicorn, WhiteNoise |
| Tooling | uv (dependencies and lockfile), Ruff (lint and format) |
| Testing | pytest, pytest-django, pytest-cov, time-machine |
| Infrastructure | Docker (multi-stage image), Docker Compose (local PostgreSQL), GitHub Actions CI |

## Architecture and key design decisions

- **The server is the source of truth.** Questions are sent without the correct answer. The correct choice is revealed only in the answer response. Points, response time and correctness are computed in the service layer (`apps/quiz/services.py`). Views stay thin, and clients only display results.
- **Per-session choice IDs.** Choices are exposed as IDs `1–4` in a per-session shuffled order rather than as database IDs. The loader always creates the correct choice first, so database IDs would give away the answer.
- **Stateless, cookie-free sessions.** Starting a game returns a one-time `session_token`, which the client sends in an `X-Session-Token` header. There are no cookies, so no CSRF handling is needed, and mobile clients work unchanged. Only a SHA-256 hash of the token is stored.
- **Server-side timing with network tolerance.** Each question has a server timestamp (`served_at`) that is scheduled slightly in the future: +3 s for the 3-2-1 countdown before the first question and +0.8 s for answer feedback afterwards. Clients receive `starts_in_ms` and `remaining_ms`, so they never depend on the device clock. Answers are accepted up to 5000 ms plus a 750 ms latency grace period. Questions whose time ran out are closed automatically on the next request, and games expire after 30 minutes (`410`).
- **Scoring formula.** A correct answer is worth `100 + floor(50 × (5000 − response_ms) / 5000)` points, so 100–150 per question and at most 3000 per game. Wrong or timed-out answers score 0. Leaderboard ties are broken by total time, then by submission time.
- **Concurrency safety.** Every state change runs in a transaction with `SELECT … FOR UPDATE` on the session row, so double submissions cannot race.
- **Rate limiting.** DRF scoped throttles per IP (per minute): starting a game 30, answers 120, score submissions 10, reads 300. Limits are configurable through environment variables.
- **Consistent error format.** Every error, including validation, 404 and throttling errors, uses the shape `{"error": {"code": "...", "message": "...", "details": {...}}}` with stable, machine-readable codes such as `session_expired` and `question_mismatch`.
- **Operational details.**
  - The health check (`/api/v1/health/`) runs a `SELECT 1` and is answered before host validation.
  - A data migration seeds the categories.
  - An idempotent `load_questions` command loads and validates the question files and has a `--check` mode.
  - A `cleanup_sessions` command expires and purges old sessions.
  - Settings are split into `base` / `dev` / `test` / `prod`.
- **Tests.** There are 223 tests running against real PostgreSQL, with about 98% coverage of `apps/`, and time is frozen in tests with time-machine. CI runs Ruff, a missing-migrations check, question-file validation, OpenAPI schema validation, the test suite and a Docker build.

## API overview

All endpoints live under `/api/v1/`. Session endpoints require the `X-Session-Token` header.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/health/` | Health check (`{"status": "ok"}`) |
| `GET` | `/api/v1/categories/` | Active categories |
| `POST` | `/api/v1/sessions/` | Start a game (`{"category": "<slug>", "client_type": "web\|ios\|android"}`) and get the token and first question |
| `GET` | `/api/v1/sessions/{id}/current/` | Current game state (used to resync after a reload or app resume) |
| `POST` | `/api/v1/sessions/{id}/answers/` | Submit an answer (`choice_id: null` on timeout) and get the result and next question |
| `GET` | `/api/v1/sessions/{id}/result/` | Final score, correct count and total time |
| `POST` | `/api/v1/sessions/{id}/score/` | Save the score with a player name (once per game) |
| `GET` | `/api/v1/leaderboard/?category=<slug>` | Top 10 for a category |

Interactive docs are at **`/api/docs/`** (Swagger UI) and the raw schema is at `/api/schema/`. The admin panel is at `/admin/`.

## Getting started

**Prerequisites:** [Docker](https://www.docker.com/) (for PostgreSQL) and [uv](https://docs.astral.sh/uv/). uv installs Python 3.14 if it is missing.

```bash
git clone https://github.com/busracankit/RapidQuizBackend.git
cd RapidQuizBackend

cp .env.example .env               # local defaults; set your own DJANGO_SECRET_KEY
docker compose up -d db            # PostgreSQL 18 on localhost:5432
uv sync                            # install dependencies into .venv
uv run manage.py migrate           # create tables and seed the 5 categories
uv run manage.py load_questions    # load the 300 questions from data/questions/
uv run manage.py createsuperuser   # optional: an account for /admin/
uv run manage.py runserver 0.0.0.0:8000
```

Check that it works:

```bash
curl http://localhost:8000/api/v1/health/
# {"status":"ok"}
```

**Android emulator:** the emulator reaches your machine at `10.0.2.2`, so add it to `DJANGO_ALLOWED_HOSTS` in `.env`. Otherwise Django returns `400 Bad Request`:

```
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,10.0.2.2
```

**Web client:** the [frontend](https://github.com/busracankit/RapidQuizFrontend) dev server runs on `http://localhost:5173`, which is already allowed in `CORS_ALLOWED_ORIGINS`.

## Running tests

The tests need the PostgreSQL container from the previous step (`docker compose up -d db`).

```bash
uv run pytest                      # 223 tests
uv run pytest --cov                # with coverage
uv run ruff check . && uv run ruff format --check .
```

## Project structure

```
RapidQuizBackend/
├── apps/
│   ├── quiz/            # categories, questions, game sessions; services.py holds the game rules
│   ├── leaderboard/     # score entries, ranking, name validation and profanity filter
│   └── api_tests/       # end-to-end API tests
├── config/
│   ├── settings/        # base / dev / test / prod
│   ├── api.py           # unified error handler, JSON 404 under /api/
│   ├── middleware.py    # health check
│   └── urls.py          # /api/v1/ routes, /api/schema/, /api/docs/
├── data/questions/      # question bank (JSON, 5 × 60)
├── docs/                # project and deployment docs (Turkish)
├── .do/app.yaml         # DigitalOcean App Platform spec (not currently deployed)
├── Dockerfile           # multi-stage production image (gunicorn + WhiteNoise)
├── docker-compose.yml   # local PostgreSQL
└── pyproject.toml       # dependencies and tool config (uv)
```
