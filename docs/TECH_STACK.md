# Tech Stack

Technology choices for the Accessible News Aggregator, with rationale.

---

## Core Stack

| Layer | Technology | Why |
| --- | --- | --- |
| Backend | Python 3.12+ with Flask | Lightweight, well-understood, Jinja2 built-in |
| Database | PostgreSQL 16 | Robust, multi-user, JSONB support, wide hosting availability |
| LLM | Ollama (local) via provider interface | Local inference, no API key; text generation (qwen2.5:7b) and embeddings (nomic-embed-text) |
| Frontend | Plain HTML + CSS + HTMX | No build step, no JS framework, server-rendered throughout |
| Templating | Jinja2 (Flask built-in) | Tight Flask integration, partial rendering for HTMX |
| Scheduling | APScheduler in dedicated worker container | Web and worker run as separate containers; web has zero ML/LLM deps |
| Packaging | Docker + docker-compose | Single `docker-compose up` runs everything |

---

## Python Dependencies

| Package | Purpose |
| --- | --- |
| Flask | Web framework |
| psycopg2-binary | PostgreSQL driver |
| APScheduler | Background job scheduling (fetch + rewrite) |
| feedparser | RSS/Atom feed parsing |
| httpx | HTTP client for feed fetching |
| ollama | Ollama Python client (LLM chat + embeddings) |
| python-dotenv | Load `.env` for secrets |
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
│   │   ├── provider.py      # Abstract LLM interface + OllamaProvider
│   │   ├── embeddings.py    # Embedding provider (Ollama nomic-embed-text)
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
├── Dockerfile                   # Multi-target: web (slim), worker (full)
├── requirements.txt            # Worker: feedparser, trafilatura, ollama, etc.
├── requirements-web.txt       # Web: slim deps only (no ollama, no feed processing)
└── .env.example                # Template for secrets (no LLM API keys needed)
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

# Pipeline commands (run in worker container)
docker compose exec worker python -m app.worker_cli fetch-feeds
docker compose exec worker python -m app.worker_cli run-pipeline

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

Four services: PostgreSQL, Ollama (LLM/embeddings), the Flask web app (slim image), and the worker (feed processing + ollama client).

- **ollama** — Runs Ollama server. Models (qwen2.5:7b, nomic-embed-text) are pulled on first start via `ollama-init`. Use `docker-compose.gpu.yml` for GPU acceleration.
- **web** — Gunicorn serves the Flask app. Uses `requirements-web.txt` (no ollama, no feed processing). Runs `alembic upgrade head` on startup, then Gunicorn.
- **worker** — Runs APScheduler (`python -m app.scheduler`) for scheduled jobs and polls the `rewrite_requests` queue for on-demand rewrites. Uses `requirements.txt` (includes ollama Python client). Connects to ollama service for LLM and embeddings. Processing CLI commands run here: `docker compose exec worker python -m app.worker_cli fetch-feeds`, etc.

```yaml
# docker-compose.yml (simplified)
services:
  ollama:
    image: ollama/ollama
    volumes:
      - ollama_data:/root/.ollama
    # ...

  db:
    image: postgres:16-alpine
    # ...

  web:
    build:
      context: .
      target: web
    ports:
      - "5000:5000"
    command: sh -c "alembic upgrade head && gunicorn -b 0.0.0.0:5000 app:application"

  worker:
    build:
      context: .
      target: worker
    depends_on:
      ollama-init:
        condition: service_completed_successfully
    environment:
      OLLAMA_HOST: http://ollama:11434
    command: python -m app.scheduler
    # ...
```

`docker-compose.override.yml` provides dev overrides: bind mounts for live reload, `flask run --debug` for the web service, exposed ports. The `.env` file contains the database password. No LLM API keys required. An `.env.example` template is provided in the repo.

**Dev tools:** Lefthook (git hooks) is a standalone binary; install via your package manager or from [lefthook.dev](https://lefthook.dev). Run `lefthook install` after cloning.

### GPU troubleshooting (Ollama using CPU instead of GPU)

If Ollama uses high CPU but negligible GPU utilization:

1. **Verify GPU inside container:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec ollama nvidia-smi
   ```
   If this fails, the GPU is not passed to the container.

2. **Check Ollama logs for GPU detection:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs ollama
   ```
   Look for "Nvidia GPU" or "CUDA" — or errors like "no compatible GPUs", "cudart", "libcuda".

3. **WSL2 + Docker Desktop:** Add the NVIDIA runtime to Docker Engine (Settings → Docker Engine):
   ```json
   "runtimes": {
     "nvidia": {
       "path": "nvidia-container-runtime",
       "runtimeArgs": []
     }
   }
   ```
   Then restart Docker Desktop.

4. **NVIDIA Container Toolkit:** On Linux/WSL2, install:
   ```bash
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure
   ```

5. **Recreate with GPU override:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml down ollama
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
   ```

---

## LLM Provider Interface

The app never calls Ollama directly. All LLM access goes through `app/llm/provider.py`, which defines an abstract `LLMProvider` class. The only implementation is `OllamaProvider`, which connects to the Ollama service via HTTP. Config in `config/app.yaml`: `llm.model` (default: `qwen2.5:7b`), `llm.host` (default: `http://ollama:11434`). No API key required.

## Embedding Provider

Article clustering uses embeddings for similarity via **Ollama** (`nomic-embed-text`). Config: `embeddings.model`, `embeddings.host`. No API key required.

---

## Scheduling Model

APScheduler runs in the dedicated `worker` container only (`python -m app.scheduler`). It is never started inside the `web` container. The web container has zero imports from `app/llm/`, `app/feed/`, `app/extraction/`, or `app/clustering/` — it is a thin HTTP layer.

Background jobs in the worker:

1. **Fetch jobs** — poll feeds per their configured interval. Articles are stored centrally in the `articles` table.
2. **Rewrite jobs** — run at a configurable daily time (default: early morning). For each active user, rewrite new articles that haven't been cached yet for their profile.
3. **Rewrite request poller** — every 60 seconds, claims pending rows from the `rewrite_requests` table. When a user saves setup/settings with regeneration-affecting changes, the web route inserts a row; the worker picks it up and runs `run_rewrite_for_user`. No LLM calls in the web process.

When a user opens the app, content is already ready. No waiting.

### CLI Commands

| Command | Where | Purpose |
| --- | --- | --- |
| `flask seed-sources` | Web container | Seed sources from config (lightweight) |
| `flask make-admin <email>` | Web container | Grant admin access |
| `flask show-rewrite-failures` | Web container | List recent rewrite failures (DB read) |
| `python -m app.worker_cli fetch-feeds` | Worker container | Run feed fetcher once |
| `python -m app.worker_cli enrich-articles` | Worker container | Run enrichment once |
| `python -m app.worker_cli cluster-articles` | Worker container | Run clustering once |
| `python -m app.worker_cli rewrite-articles` | Worker container | Run rewrite batch once |
| `python -m app.worker_cli run-pipeline` | Worker container | Full pipeline: seed → fetch → enrich → cluster → rewrite |
