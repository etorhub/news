## TECH STACK

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
