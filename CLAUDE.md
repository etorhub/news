# CLAUDE.md — Accessible News Aggregator

Context document for an AI-powered news aggregator built for people who struggle with the way news is currently delivered.

---

## Problem Statement

Most news interfaces are built for engagement, not comprehension. For people with motor or cognitive difficulties — Parkinson's disease being the origin case — they are actively hostile: cluttered layouts, small touch targets, dense sentences with nested clauses, and no way to control the pace or depth of information.

The content itself is often fine. The format is the barrier. This project places an LLM between raw news and the reader, reshaping each article to fit the reader rather than asking the reader to adapt to the article.

---

## Who We Are Building For (Now)

The initial target is a person with Parkinson's disease, or a comparable motor or cognitive condition, who:

- Cannot reliably navigate standard news websites (small buttons, unpredictable layouts, accidental clicks)
- Finds long, subordinate-heavy sentences difficult to process
- Benefits from large fonts, high contrast, and minimal visual noise
- May rely on text-to-speech rather than sustained reading

Critically, **neither the end user nor the caregiver ever accesses the codebase**. Both access the platform (web app) only. Their only requirement is to create a user account. The caregiver typically completes the initial configuration; the end user reads the content. This shapes every decision about onboarding, profile management, and configuration.

---

## Deployment Model

The project is open source (AGPL). Whether self-hosted or hosted, **end users and caregivers always access the platform, never the codebase**. They create a user account, complete the configuration page, and see content. No technical setup required on their side.

A family member with basic technical ability can self-host for a relative. A hosted, managed version will also be offered for families who want the benefits without running infrastructure. Both versions share the same codebase.

---

## Key Features

### MVP

Refer to `docs/MVP_PLAN.md` for the canonical phased plan: discovery, fetching, processing, platform (auth, profile config, feed, daily digest).

### Accessibility (non-negotiable, not optional)

- Large font, high contrast mode
- Large touch targets throughout — every interactive element must be usable with imprecise motor control
- Text-to-speech per article
- One-article-at-a-time mode, no infinite scroll
- Configurable detail level: headline → summary → full simplified article

### Caregiver-facing

- Remote profile configuration (location, sources, topics, language, negative news filter, rewrite tone) without requiring the end user to touch settings
- Soft daily notification: "You have 5 new articles"
- Account management designed to be set up once and left alone

---

## Tech Stack

- **Backend:** Python 3.12+ with Flask
- **Database:** SQLite (single file, no server required)
- **LLM:** Ollama (local, default) — abstracted behind a provider interface
- **Frontend:** Plain HTML + CSS + HTMX
- **Templating:** Jinja2 (Flask built-in)
- **Scheduling:** APScheduler (embedded in Flask app, no separate cron required)
- **Packaging:** Docker + docker-compose (single `docker-compose up` to run everything)

---

## Architecture Constraints

These are hard rules, not preferences:

- **Flask routes return HTML only.** Never return JSON to the frontend. Every endpoint renders and returns a Jinja2 template partial. This is HATEOAS — the server owns all state and rendering.
- **HTMX is the only frontend dependency.** No JavaScript frameworks. No build step. No npm. HTMX is loaded via a single CDN script tag.
- **LLM calls are always abstracted.** Never call Ollama, OpenAI, or Anthropic directly from a route. Always go through the provider interface in `llm/provider.py`.
- **Processing is on-demand, per session.** Articles are fetched and rewritten when the user opens the app for the first time that day. Results are cached in SQLite. A user who doesn't open the app pays nothing.
- **Config is never hardcoded.** YAML files define the catalog of available sources/topics and app-level settings. User preferences (location, selected sources, selected topics, filter toggle, rewrite tone, language) live in SQLite, set via the web UI.

---

## Project Structure

```
/
├── app/
│   ├── routes/          # Flask blueprints — one per domain area
│   ├── templates/       # Jinja2 templates and partials
│   │   └── partials/    # HTMX fragment templates
│   ├── llm/
│   │   ├── provider.py  # Abstract LLM interface
│   │   └── prompts/     # Prompt templates (plain text files)
│   ├── feed/            # RSS fetching and normalisation
│   ├── db/              # SQLite access layer
│   └── tts/             # Text-to-speech helpers
├── config/
│   ├── sources.yaml     # Catalog of available RSS feeds and API sources (user selections in SQLite)
│   └── app.yaml         # App-level config (port, LLM provider, etc.)
├── CLAUDE.md
├── ARCHITECTURE.md
├── docker-compose.yml
└── Dockerfile
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

## Coding Rules

- Use Python type hints throughout
- Flask routes use blueprints — never register routes directly on the app object
- Template partials (for HTMX responses) live in `templates/partials/` and follow the naming convention `{resource}_{action}.html` (e.g. `article_expanded.html`)
- Never put business logic in routes — routes call services, services do the work
- SQLite access goes through the db layer, never raw SQL in routes or services
- Every config value has a documented default in `app.yaml`

---

## What Claude Gets Wrong on This Stack

- **Returning JSON from Flask routes.** Every route must return `render_template(...)` or `render_template_string(...)`. If you find yourself writing `jsonify`, stop.
- **Adding JavaScript.** HTMX attributes on HTML elements handle all interactivity. There is no `static/js/` directory.
- **Calling the LLM directly.** Always use `from app.llm.provider import get_provider` and call through the interface.
- **Hardcoding source URLs or prompts.** These live in config files.
- **Putting user preferences in YAML files.** User profile settings live in SQLite, set through the setup wizard. Only the source catalog and app-level config belong in YAML.

---

## Content Sourcing

RSS + open publishers are the primary source. Full article text is required for meaningful simplification — RSS-level text is the fallback for paywalled outlets, not the target. Open Catalan and Spanish publishers (RTVE, CCMA/3Cat, Vilaweb, El Crític, NacióDigital) are the initial priority and provide full content without legal risk.

No User-Agent spoofing. No paywalled content bypass. Every article links to the original source.

For automated news source discovery (finding feeds by location, validation, quality scoring), see `docs/news_source_discovery_agent.md`.

---

## Legal Considerations

- Self-hosted, private use: minimal legal risk
- Hosted product: always cite and link to the original; transformation must be substantive; never reproduce content that substitutes for the original
- Copyright remains with the publisher — this product is a reading aid, not a republisher

---

## Design Principles

- **Accessibility is a constraint, not a feature.** Every UI decision is evaluated against the primary user's motor and cognitive profile first.
- **Caregiver setup, user operation.** The caregiver creates the account and configures via the web UI; daily use requires none.
- **Config-driven throughout.** App config (source catalog, LLM prompts, server settings) lives in YAML. User preferences live in SQLite, set via the setup wizard and settings page.
- **Self-hosted must be genuinely usable.** Whoever deploys (e.g. a family member) should be able to run and maintain it without ongoing help. End users and caregivers using the platform never touch deployment.

---

## Out of Scope (for now)

- Paywalled content bypass
- Training or fine-tuning a custom model
- Native mobile app (web-first, responsive)
- Social or sharing features
- Additional user personas beyond the primary target
