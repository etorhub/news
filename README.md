# Accessible News Aggregator

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://opensource.org/licenses/AGPL-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed?logo=docker&logoColor=white)](https://www.docker.com/)
[![HTMX](https://img.shields.io/badge/HTMX-2.x-3d7fcf?logo=htmx&logoColor=white)](https://htmx.org/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama_local-000000)](https://ollama.ai/)

A news reader built for people who struggle with the way news is currently delivered.

Most news interfaces are designed for engagement, not comprehension. For people with motor or cognitive difficulties — Parkinson's disease being the origin case — they are actively hostile: cluttered layouts, small touch targets, dense sentences, and no way to control the pace or depth of information.

This project places an LLM between raw news and the reader, reshaping each article to fit the reader rather than asking the reader to adapt to the article.

---

## What It Does

- Fetches news from RSS feeds and open publishers on a schedule
- Rewrites each article via LLM for clarity: short sentences, simple vocabulary, configurable tone
- Presents content in a clean, accessible interface with large fonts, high contrast, and large touch targets
- Supports multiple users with independent profiles and preferences
- Provides text-to-speech when the browser supports it
- Shows a daily digest — content is ready when you open the app, no waiting

## Who It's For

The primary user is someone with Parkinson's disease or a comparable motor/cognitive condition. A caregiver creates the account and configures preferences; the end user opens the app and reads.

Neither the end user nor the caregiver ever touches the codebase. They access the web app only.

---

## Quick Start

### Prerequisites

- Docker and docker-compose

### Setup

```bash
git clone https://github.com/accessible-news/aggregator.git
cd aggregator

# Copy the environment template and fill in values
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and SECRET_KEY (no LLM API key needed — uses local Ollama)

# Start everything
docker-compose up

# Seed news sources from config (required before fetch-feeds)
docker compose exec web flask seed-sources
```

The app starts at `http://localhost:5000`. Create an account, complete the setup wizard, and you'll see your first articles after the next scheduled fetch/rewrite cycle.

### Admin dashboard

Operators can monitor ingestion pipelines, job history, and system health at `/admin`. Access requires admin privileges.

A default admin account is created by migrations: **admin@admin.com** / **admin**. To grant admin to another user:

```bash
docker compose exec web flask make-admin your@email.com
```

See [docs/ADMIN_DASHBOARD.md](docs/ADMIN_DASHBOARD.md) for full documentation.

### Running scheduler jobs manually

The scheduler runs four jobs on a schedule: fetch feeds, enrich articles (extract full text), cluster articles (embed + group), and rewrite articles (LLM simplification). You can run any of them manually:

| Command | Where | Description |
| ------- | ----- | ----------- |
| `flask seed-sources` | Web | Load sources from config/sources.yaml (run once before fetch) |
| `python -m app.worker_cli fetch-feeds` | Worker | Fetch all due RSS feeds |
| `python -m app.worker_cli enrich-articles` | Worker | Extract full article content for pending articles |
| `python -m app.worker_cli cluster-articles` | Worker | Embed and cluster today's articles |
| `python -m app.worker_cli rewrite-articles` | Worker | Rewrite articles for all user profiles |
| `python -m app.worker_cli run-pipeline` | Worker | Full pipeline once (seed → fetch → enrich → cluster → rewrite) |

Pipeline order: seed sources first (once), then fetch, enrich, cluster, rewrite.

With Docker:

```bash
docker compose exec web flask seed-sources
docker compose exec worker python -m app.worker_cli fetch-feeds
docker compose exec worker python -m app.worker_cli run-pipeline
```

### Running Locally (without Docker)

```bash
# Requires Python 3.12+ and a running PostgreSQL instance
pip install -r requirements.txt
flask run
```

---

## Tech Stack

| Layer      | Technology                                  |
| ---------- | ------------------------------------------- |
| Backend    | Python 3.12+ / Flask                        |
| Database   | PostgreSQL 16                               |
| LLM        | Ollama (local, no API key)                  |
| Frontend   | HTML + CSS + HTMX (no JavaScript frameworks) |
| Scheduling | APScheduler (worker container)               |
| Packaging  | Docker + docker-compose                     |

See [docs/TECH_STACK.md](docs/TECH_STACK.md) for full details.

---

## Documentation

| Document                                                                   | Description                                                                                                                           |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| [CONTRIBUTING.md](CONTRIBUTING.md)                                         | How to contribute — setup, code standards, commits, PRs                                                                                |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)                                   | Community standards and enforcement                                                                                                   |
| [SECURITY.md](SECURITY.md)                                                 | Security policy and vulnerability reporting                                                                                           |
| [CLAUDE.md](CLAUDE.md)                                                     | AI assistant context (Claude Code) — coding rules, architecture constraints, design principles                                        |
| [.cursor/rules/](.cursor/rules/)                                           | Cursor IDE rules — same context via `project-context.mdc` (always apply) plus architecture, accessibility, LLM, news-source-discovery |
| [docs/TECH_STACK.md](docs/TECH_STACK.md)                                   | Tech stack, project structure, dependencies, Docker setup                                                                             |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)                               | System architecture, database schema, component map, request lifecycle                                                                |
| [docs/ADMIN_DASHBOARD.md](docs/ADMIN_DASHBOARD.md)                         | Admin dashboard: pipeline monitoring, job history, user activity, incidents                                                           |
| [docs/MVP_PLAN.md](docs/MVP_PLAN.md)                                       | Phased MVP plan with tasks and success criteria                                                                                       |
| [docs/news_source_discovery_agent.md](docs/news_source_discovery_agent.md) | News source discovery pipeline specification                                                                                          |

---

## Accessibility

Accessibility is a constraint, not a feature. Every UI decision is evaluated against the primary user's motor and cognitive profile first:

- Minimum 48x48px touch targets on all interactive elements
- Base font size 22px, line height 1.6
- WCAG AA contrast minimum (4.5:1), AAA target (7:1) in high-contrast mode
- One article at a time — no infinite scroll
- Text-to-speech via Web Speech API (hidden when not supported)
- Semantic HTML throughout
- No hover-only interactions, no timed content

---

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.

The project is a reading aid, not a republisher. Every article links to and credits the original source. Copyright remains with the publisher.
