# Tech Stack

Technology choices for the Accessible News Aggregator, with rationale.

---

## Core Stack

| Layer | Technology | Why |
| --- | --- | --- |
| Backend | Python 3.12+ with Flask | Lightweight, well-understood, Jinja2 built-in |
| Database | PostgreSQL 16 | Robust, multi-user, JSONB support, wide hosting availability |
| LLM | External APIs (Anthropic, OpenAI, Gemini) via provider interface | No local GPU required, production-grade reliability, easy setup |
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
| python-dotenv | Load `.env` for API keys |
| bcrypt | Password hashing |
| ruff | Linting and formatting |
| pytest | Testing |

---

## Project Structure

```
/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Loads config/*.yaml
│   ├── routes/              # Flask blueprints — one per domain area
│   ├── services/            # Business logic — routes call services
│   ├── templates/           # Jinja2 templates
│   │   └── partials/        # HTMX fragment templates
│   ├── llm/
│   │   ├── provider.py      # Abstract LLM interface + factory
│   │   ├── providers/       # Anthropic, OpenAI, Gemini implementations
│   │   └── prompts/         # Prompt templates (plain .txt files)
│   ├── feed/                # RSS fetching and normalisation
│   ├── db/                  # PostgreSQL access layer
│   └── tts/                 # Text-to-speech helpers (browser API prep)
├── config/
│   ├── sources.yaml         # Catalog of available RSS feeds and API sources
│   └── app.yaml             # App-level config (LLM provider, schedule, etc.)
├── tests/                   # pytest test suite
├── docs/                    # Project documentation
├── .cursor/rules/           # Cursor IDE rules
├── CLAUDE.md                # AI assistant context
├── README.md
├── docker-compose.yml
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

# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .
```

---

## Docker Composition

Two services: the Flask app and PostgreSQL.

```yaml
# docker-compose.yml (simplified)
services:
  app:
    build: .
    ports:
      - "5000:5000"
    depends_on:
      - db
    env_file:
      - .env
    volumes:
      - ./config:/app/config

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=news
      - POSTGRES_USER=news
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

volumes:
  pgdata:
```

The `.env` file contains API keys and the database password. An `.env.example` template is provided in the repo.

---

## LLM Provider Interface

The app never calls an LLM SDK directly. All LLM access goes through `app/llm/provider.py`, which defines an abstract `LLMProvider` class. Concrete implementations exist for Anthropic, OpenAI, and Gemini. The active provider is selected from `config/app.yaml`.

This makes it straightforward to add new providers (including local ones like Ollama for self-hosters who prefer it).

---

## Scheduling Model

APScheduler runs two types of background jobs inside the Flask process:

1. **Fetch jobs** — poll feeds per their configured interval (high/medium/low frequency tiers). Articles are stored centrally in the `articles` table with full text when available.
2. **Rewrite jobs** — run at a configurable daily time (default: early morning). For each active user, rewrite new articles that haven't been cached yet for their profile.

When a user opens the app, content is already ready. No waiting.
