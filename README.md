# Accessible News Aggregator

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
- An API key for at least one LLM provider (Anthropic, OpenAI, or Gemini)

### Setup

```bash
git clone https://github.com/your-org/news.git
cd news

# Copy the environment template and fill in your API key
cp .env.example .env
# Edit .env with your LLM API key and a database password

# Start everything
docker-compose up

# Seed news sources from config (required before fetch-feeds)
docker compose exec web flask seed-sources
```

The app starts at `http://localhost:5000`. Create an account, complete the setup wizard, and you'll see your first articles after the next scheduled fetch/rewrite cycle.

### Admin dashboard

Operators can monitor ingestion pipelines, job history, and system health at `/admin`. Access requires admin privileges. Grant them with:

```bash
flask make-admin your@email.com
```

See [docs/ADMIN_DASHBOARD.md](docs/ADMIN_DASHBOARD.md) for full documentation.

### Running scheduler jobs manually

The scheduler runs four jobs on a schedule: fetch feeds, enrich articles (extract full text), cluster articles (embed + group), and rewrite articles (LLM simplification). You can run any of them manually via Flask CLI:

| Command | Description |
| ------- | ----------- |
| `flask seed-sources` | Load sources from config/sources.yaml into the database (run once before fetch) |
| `flask fetch-feeds` | Fetch all due RSS feeds |
| `flask enrich-articles` | Extract full article content for pending articles |
| `flask cluster-articles` | Embed and cluster today's articles |
| `flask rewrite-articles` | Rewrite articles for all user profiles |
| `flask run-pipeline` | Run the full pipeline once (seed → fetch → enrich → cluster → rewrite) |

Pipeline order matters: seed sources first (once), then fetch, enrich, cluster, rewrite. Use `flask run-pipeline` to run the full pipeline (seed is included).

With Docker, run commands inside the web container (which has the same codebase as the scheduler):

```bash
docker compose exec web flask seed-sources
docker compose exec web flask fetch-feeds
docker compose exec web flask run-pipeline
```

### Running Locally (without Docker)

```bash
# Requires Python 3.12+ and a running PostgreSQL instance
pip install -r requirements.txt
flask run
```

---

## Tech Stack

| Layer      | Technology                                            |
| ---------- | ----------------------------------------------------- |
| Backend    | Python 3.12+ / Flask                                  |
| Database   | PostgreSQL 16                                         |
| LLM        | Anthropic, OpenAI, or Gemini (via provider interface) |
| Frontend   | HTML + CSS + HTMX (no JavaScript frameworks)          |
| Scheduling | APScheduler                                           |
| Packaging  | Docker + docker-compose                               |

See [docs/TECH_STACK.md](docs/TECH_STACK.md) for full details.

---

## Documentation

| Document                                                                   | Description                                                                                                                           |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
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
