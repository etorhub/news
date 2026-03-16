# Tech Stack

Technology choices for the Accessible News Aggregator, with rationale.

---

## Core Stack

| Layer | Technology | Why |
| --- | --- | --- |
| Backend | Python 3.12+ with Flask | Lightweight, well-understood, Jinja2 built-in |
| Database | PostgreSQL 16 | Robust, multi-user, JSONB support, wide hosting availability |
| LLM | External APIs (Anthropic, OpenAI, Gemini) or local (transformers + PyTorch) via provider interface | Cloud for reliability; local for privacy/air-gapped, no API key |
| Frontend | Plain HTML + CSS + HTMX | No build step, no JS framework, server-rendered throughout |
| Templating | Jinja2 (Flask built-in) | Tight Flask integration, partial rendering for HTMX |
| Scheduling | APScheduler (embedded in Flask process) | No external cron or task queue; fetching and rewriting run on a schedule |
| Packaging | Docker + docker-compose | Single `docker-compose up` runs everything |

---

## Python Dependencies

| Package | Purpose |
| --- | --- |
| Flask | Web framework |
| psycopg2-binary | PostgreSQL driver |
| APScheduler | Background job scheduling (fetch + rewrite) |
| feedparser | RSS/Atom feed parsing |
| httpx | HTTP client for feed fetching and LLM API calls |
| anthropic | Anthropic Claude API client |
| openai | OpenAI API client |
| google-generativeai | Google Gemini API client |
| sentence-transformers | Local embeddings for article clustering (default) |
| transformers | Hugging Face models (used by sentence-transformers and local LLM) |
| accelerate | Device handling and model loading for local LLM |
| python-dotenv | Load `.env` for API keys |
| bcrypt | Password hashing |
| alembic | Database migrations |
| ruff | Linting and formatting |
| mypy | Static type checking |
| pytest | Testing |
| commitizen | Conventional commits and version bumping |

---

## Project Structure

```
/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Loads config/*.yaml
│   ├── routes/              # Flask blueprints — reader, auth, setup, settings, admin
│   ├── services/            # Business logic — routes call services
│   ├── templates/           # Jinja2 templates
│   │   └── partials/        # HTMX fragment templates
│   ├── llm/
│   │   ├── provider.py      # Abstract LLM interface + factory
│   │   ├── embeddings.py   # Embedding provider (local sentence-transformers)
│   │   ├── providers/       # Anthropic, OpenAI, Gemini implementations
│   │   └── prompts/         # Prompt templates (plain .txt files)
│   ├── feed/                # RSS fetching and normalisation
│   └── db/                  # PostgreSQL access layer (includes admin queries)
├── alembic/                 # Database migration scripts (Alembic)
│   ├── env.py
│   └── versions/            # Versioned migration files
├── config/
│   ├── sources.yaml         # Catalog of available RSS feeds and API sources
│   └── app.yaml             # App-level config (LLM provider, schedule, etc.)
├── tests/                   # pytest test suite
├── docs/                    # Project documentation
├── .cursor/rules/           # Cursor IDE rules (project-context.mdc = full CLAUDE.md equivalent)
├── CLAUDE.md                # AI assistant context (Claude Code)
├── README.md
├── pyproject.toml           # Ruff, Mypy, Pytest, Commitizen config
├── lefthook.yml             # Git hooks (pre-commit, pre-push, commit-msg)
├── docker-compose.yml
├── docker-compose.override.yml  # Dev overrides (bind mounts, flask run --debug)
├── Dockerfile
├── requirements.txt
└── .env.example             # Template for API keys and secrets
```

---

## Key Commands

```bash
# Run the app locally (no Docker)
flask run

# Run with Docker (recommended)
docker-compose up

# Grant admin access to a user (for /admin dashboard)
flask make-admin user@example.com

# Install git hooks (run after cloning)
lefthook install

# Conventional commit (interactive)
cz commit
# or: cz c

# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .

# Type check
mypy .
```

### Admin dashboard

Operators can access `/admin` to monitor ingestion pipelines, job history, feed health, user activity, and incidents. Admin access is granted via `flask make-admin <email>`. See [docs/ADMIN_DASHBOARD.md](ADMIN_DASHBOARD.md) for details.

---

## Docker Composition

Three services: PostgreSQL, the Flask web app, and the APScheduler process.

```yaml
# docker-compose.yml (simplified)
services:
  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=news
      - POSTGRES_USER=news
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U news"]
      interval: 5s
      timeout: 5s
      retries: 5

  web:
    build: .
    ports:
      - "5000:5000"
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    volumes:
      - ./config:/app/config
    command: gunicorn -b 0.0.0.0:5000 "app:create_app()"

  scheduler:
    build: .
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    volumes:
      - ./config:/app/config
    command: python -m app.scheduler

volumes:
  pgdata:
```

`docker-compose.override.yml` provides dev overrides: bind mounts for live reload, `flask run --debug` for the web service, exposed ports. The `.env` file contains API keys and the database password. An `.env.example` template is provided in the repo.

**Dev tools:** Lefthook (git hooks) is a standalone binary; install via your package manager or from [lefthook.dev](https://lefthook.dev). Run `lefthook install` after cloning.

---

## LLM Provider Interface

The app never calls an LLM SDK directly. All LLM access goes through `app/llm/provider.py`, which defines an abstract `LLMProvider` class. Concrete implementations exist for Anthropic, OpenAI, Gemini, and **local** (Hugging Face transformers + PyTorch). The active provider is selected from `config/app.yaml`.

For `provider: local`, no API key is required. Models run in-process via `transformers` and PyTorch. Use `model` (Hugging Face model ID) or `model_path` (local directory for air-gapped use). Default model: `HuggingFaceH4/zephyr-3b-beta`.

## Embedding Provider

Article clustering uses embeddings for similarity via **local** `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) — no API key, runs on CPU.

---

## Scheduling Model

APScheduler runs in the dedicated `scheduler` container only (`python -m app.scheduler`). It is never started inside the `web` container. Running APScheduler inside Gunicorn causes every worker to spawn its own scheduler, executing every job N times.

Two types of background jobs:

1. **Fetch jobs** — poll feeds per their configured interval (high/medium/low frequency tiers). Articles are stored centrally in the `articles` table with full text when available.
2. **Rewrite jobs** — run at a configurable daily time (default: early morning). For each active user, rewrite new articles that haven't been cached yet for their profile.

When a user opens the app, content is already ready. No waiting.
