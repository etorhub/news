# ARCHITECTURE.md

Technical reference for the Accessible News Aggregator. Update this document when architectural decisions change.

---

## System Overview

A Flask web application that fetches news from RSS feeds and open publisher APIs on a schedule, rewrites each article via an external LLM to match a reader's accessibility profile, and presents the result in a clean, accessible reader interface.

The system has no client-side rendering. Flask renders all HTML server-side via Jinja2. HTMX makes targeted requests to Flask routes and swaps HTML fragments into the page. PostgreSQL stores user accounts, fetched articles, rewritten content, and all configuration.

Fetching and rewriting happen on a background schedule (APScheduler). When a user opens the app, content is already ready.

---

## Request Lifecycle

### First-time setup

```
User opens app
    → GET /
    → Flask checks: is user logged in?
    → No: redirect to GET /login (or /register for new users)
    → After login, Flask checks: does this user have a profile?
    → No: redirect to GET /setup
    → Caregiver fills in: location, language, sources, topics, negative news filter, rewrite tone
    → POST /setup → validate, store in PostgreSQL → trigger initial rewrite job → redirect to /
```

### Normal open (content already scheduled)

```
User opens app
    → GET /
    → Flask queries PostgreSQL: get today's articles + cached rewrites for this user's profile_hash
    → Returns full article list immediately — no LLM calls made
    → User sees today's digest with 3-line summaries
```

### New user before first scheduled rewrite

```
User opens app for the first time after completing setup
    → GET /
    → Flask checks: any cached rewrites for this user's profile?
    → No: return page with message "Your articles are being prepared"
    → APScheduler picks up the new user's profile in the next rewrite cycle
    → On next visit (or via HTMX polling), content is ready
```

### Article expansion

```
User taps "Read more"
    → hx-get="/articles/{id}/expand"
    → Flask queries PostgreSQL: get cached full rewrite for this article + profile_hash
    → Returns partials/article_expanded.html with cached content
    → HTMX swaps the partial into #article-{id}
```

---

## Component Map

### `app/feed/`

Responsible for fetching and normalising content from RSS feeds and APIs.

For automated source discovery (location-based discovery, feed detection, quality scoring), see `docs/news_source_discovery_agent.md`. The Cursor rule `.cursor/rules/news-source-discovery.mdc` applies when working in this area.

- `fetcher.py` — fetches RSS feeds via `feedparser`, returns normalised `RawArticle` objects
- `normaliser.py` — converts raw feed entries to a common schema regardless of source
- `sources.py` — loads and validates `config/sources.yaml`
- `scheduler.py` — APScheduler job definitions for feed polling (tiered by frequency)

A `RawArticle` has: `id`, `title`, `url`, `source`, `published_at`, `raw_text` (RSS description/lede), `full_text` (populated when the source provides full article content).

### `app/llm/`

The LLM abstraction layer. Nothing outside this directory calls an LLM SDK directly.

- `provider.py` — `LLMProvider` abstract base class and provider factory
- `embeddings.py` — `EmbeddingProvider` for article clustering; local sentence-transformers
- `providers/anthropic.py` — Anthropic Claude implementation
- `providers/openai.py` — OpenAI implementation
- `providers/gemini.py` — Google Gemini implementation
- `prompts/` — prompt template files (`.txt`)
- `rewriter.py` — orchestrates the rewrite: loads profile, builds prompt, calls provider, returns `RewrittenArticle`
- `scheduler.py` — APScheduler job definitions for daily rewrite cycle

### `app/services/`

Business logic. Routes call services; services do the work.

- `article_service.py` — get today's articles for a user, get digest, expand article
- `profile_service.py` — create/update user profile, compute profile_hash
- `rewrite_service.py` — rewrite articles for a profile, manage cache
- `auth_service.py` — user registration, login, session management

### `app/db/`

All PostgreSQL access. No other module writes to the database directly.

- `articles.py` — read/write for articles
- `clusters.py` — clusters, cluster_articles, cluster_rewrites
- `rewrites.py` — read/write for rewrite cache (legacy per-article)
- `sources.py` — news_sources, source_feeds, source_discovery_log
- `users.py` — read/write for users and profiles
- `admin.py` — admin dashboard queries (job runs, overview stats, feed health, incidents)
- `connection.py` — connection pool management

### `app/routes/`

Flask blueprints. Routes are thin wrappers: parse request, call service, return template.

- `reader.py` — main reader interface (`/`, `/clusters/<id>/expand`)
- `auth.py` — login, register, logout
- `setup.py` — initial configuration wizard (`GET /setup`, `POST /setup`)
- `settings.py` — configuration interface; allows editing profile fields after initial setup
- `admin.py` — admin dashboard (`GET /admin`, `GET /admin/partials/jobs`); requires `is_admin`

### `app/templates/`

Jinja2 templates. Pages extend `base.html`. HTMX responses use partials.

```
templates/
├── base.html               # Shell: nav, font settings; contains inline <script> for Web Speech API TTS only
├── index.html              # Main reader view (today's digest)
├── login.html              # Login page
├── register.html           # Registration page
├── setup.html              # Initial configuration wizard
├── settings.html           # Settings page
├── admin/
│   ├── dashboard.html      # Admin dashboard (pipelines, jobs, users, incidents)
│   └── partials/
│       └── jobs.html       # Job runs table (HTMX partial, auto-refresh)
└── partials/
    ├── article_card.html   # Summary card (one article in list)
    ├── article_expanded.html  # Full simplified article
    ├── article_list.html   # The full list of today's articles
    ├── setup_sources.html  # Source selection section for setup
    └── setup_topics.html   # Topic selection section for setup
```

---

## Database Schema

PostgreSQL 16. Multi-user from the start.

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    location TEXT,
    language TEXT NOT NULL DEFAULT 'ca',
    filter_negative BOOLEAN NOT NULL DEFAULT FALSE,
    rewrite_tone TEXT NOT NULL DEFAULT 'Short sentences. Simple vocabulary. No jargon.',
    high_contrast BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_sources (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    source_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (user_id, source_id)
);

CREATE TABLE user_topics (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    topic_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (user_id, topic_id)
);

CREATE TABLE articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source_id TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    raw_text TEXT,
    full_text TEXT,
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE rewrites (
    article_id TEXT REFERENCES articles(id) ON DELETE CASCADE,
    profile_hash TEXT NOT NULL,
    summary TEXT,
    full_text TEXT,
    rewrite_failed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (article_id, profile_hash)
);

CREATE INDEX idx_articles_source ON articles(source_id);
CREATE INDEX idx_articles_published ON articles(published_at DESC);
CREATE INDEX idx_rewrites_hash ON rewrites(profile_hash);

-- Admin dashboard: job run history (see docs/ADMIN_DASHBOARD.md)
CREATE TABLE job_runs (
    id SERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'running',
    result JSONB,
    error_message TEXT
);
CREATE INDEX idx_job_runs_job_name_started_at ON job_runs(job_name, started_at);
```

### Source tables

`articles.source_id` is a text FK whose referent depends on the deployment mode:

- **With discovery pipeline:** references `news_sources.id` (UUID cast to text). The full `news_sources`, `source_feeds`, and `source_discovery_log` tables are defined in `docs/news_source_discovery_agent.md` and are the canonical source catalog when the discovery pipeline is active.
- **Manual seed only (MVP shortcut):** `source_id` is the string `id` field from `config/sources.yaml`. No `news_sources` table is required; the YAML catalog is the source of truth.

Both modes use the same `articles` schema. The fetching layer (`app/feed/`) handles the difference. When integrating the discovery pipeline, migrate `source_id` values to UUIDs and add the FK constraint.

### Profile hash

The cache key for a rewrite is `sha256(json(profile_rewrite_fields))`. The hash includes **only fields that affect the rewrite output**, serialised as a canonical JSON object with sorted keys:

```python
import hashlib, json

def compute_profile_hash(profile: dict) -> str:
    fields = {
        "language": profile["language"],
        "rewrite_tone": profile["rewrite_tone"],
        "filter_negative": profile["filter_negative"],
    }
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True).encode()
    ).hexdigest()
```

It does **not** include source selections, topic selections, or location. Changing which sources you follow does not invalidate existing rewrites. Two users with identical language, tone, and filter settings share cached rewrites.

---

## Configuration

All config lives in `config/`. The app reads it at startup. No config is hardcoded.

### `config/app.yaml`

```yaml
llm:
  provider: anthropic        # anthropic | openai | gemini
  model: claude-sonnet-4-20250514

embeddings:
  provider: local            # sentence-transformers
  model: paraphrase-multilingual-MiniLM-L12-v2

schedule:
  fetch_interval_minutes: 60
  rewrite_cron: "0 6 * * *"  # Daily at 6am
  rewrite_batch_size: 10

processing:
  articles_per_day: 10
  summary_sentences: 3

server:
  port: 5000
  debug: false
```

> **Note:** `SECRET_KEY` is loaded directly from the environment (`.env`) by the Flask app factory — not via `app.yaml`. YAML is for non-secret config only.

### `config/sources.yaml`

Defines the catalog of available sources and their metadata. Each source should include a `topics` list. User selections are stored in PostgreSQL via the setup wizard and settings page.

```yaml
sources:
  - id: "3cat"
    name: "3Cat Notícies"
    type: rss
    url: "https://www.3cat.cat/rss/noticia/catala/rss.xml"
    language: ca
    topics: ["general"]
    full_text: true

  - id: "elcritic"
    name: "El Crític"
    type: rss
    url: "https://www.elcritic.cat/feed"
    language: ca
    topics: ["politics", "society"]
    full_text: true

  - id: "vilaweb"
    name: "Vilaweb"
    type: rss
    url: "https://www.vilaweb.cat/feed/"
    language: ca
    topics: ["general", "politics"]
    full_text: true
```

---

## LLM Processing Detail

### Prompt (reference)

```
Rewrite the following news article for a reader with these instructions:
- {rewrite_tone}
- Language: {language}
- Output format: {summary_sentences} sentence summary, then a blank line, then the full simplified article

Source article:
{article_text}

Rules:
- Preserve all factual content exactly as stated in the source
- Do not add information, context, or opinion not present in the source
- Do not shorten the article — simplify it
```

When `filter_negative` is enabled, the prompt appends:

```
- If an article describes violence, death, severe illness, or disaster in graphic detail, soften the tone or summarise it briefly without graphic content.
- If an article is primarily distressing with no informational value, omit it from the output entirely.
```

The negative filter is applied at rewrite time via the LLM prompt — not by keyword list or pre-filtering. It is a soft filter; the LLM exercises judgement.

### `rewrite_tone` valid values

The `rewrite_tone` field is a short freeform instruction string included verbatim in the LLM prompt. Recommended values (enforce via the setup wizard dropdown):

| Value (stored in DB) | Label shown to caregiver |
|---|---|
| `Short sentences. Simple vocabulary. No jargon.` | Simple (default) |
| `Very short sentences. One idea per sentence. Elementary vocabulary.` | Very simple |
| `Short sentences. Calm, reassuring tone. Avoid alarming phrasing.` | Calm |
| `Short sentences. Formal but clear. Avoid colloquialisms.` | Formal |

Store and pass the full instruction string, not a code name. The LLM prompt uses it directly. The default is `Short sentences. Simple vocabulary. No jargon.`

### Rewrite scheduling

**Active user definition:** A user is considered active for the daily rewrite job if they have completed the setup wizard (i.e., `user_profiles` row exists for that `user_id`) AND their account `is_active = TRUE`. No recency requirement — every user with a complete profile gets fresh rewrites daily. This means LLM cost scales with the number of registered, setup-complete accounts, not just recent logins.

The daily rewrite job (APScheduler):

1. Collects all active users (defined above) and their profile hashes
2. Collects today's articles (from scheduled fetch)
3. For each unique profile hash, rewrites articles that don't have a cached result
4. Stores results in the `rewrites` table

Two users with the same profile hash share cached rewrites — the LLM is never called twice for the same content + profile combination.

### Daily digest delivery

The daily digest is an **in-app experience only**. There is no email or push notification in the MVP. When a user opens the app after the rewrite job has run, they see a badge or banner: "N new articles since your last visit." This is rendered server-side from the `rewrites` table — no service worker, no push API.

The badge is shown to both the end user and the caregiver (same account). The caregiver can therefore check it from any device without special notification setup.

### Language and source mismatch

If a user sets `language = "en"` but selects Catalan-language sources, the LLM rewrites the article **in the user's configured language** (English), effectively translating it. The rewrite prompt always specifies the target language. There is no pre-filtering by source language.

Caregivers should be aware of this during setup: the setup wizard should display each source's language so they can make an informed selection. Cross-language selections are allowed; translation is automatic.

---

## Operational Rules

### Admin dashboard

Operators can monitor the system at `/admin`. Access requires `is_admin = true` on the user account. Grant via `flask make-admin <email>`. The dashboard shows job run history, feed health, article pipeline stats, clustering coverage, user activity, and auto-detected incidents. See [docs/ADMIN_DASHBOARD.md](ADMIN_DASHBOARD.md).

### APScheduler and Gunicorn workers

**Hard rule:** APScheduler must only run in the `scheduler` container (entrypoint: `python -m app.scheduler`). It must never be imported or started inside the `web` container.

If APScheduler is started inside a Gunicorn process, every worker spawns its own scheduler, causing every scheduled job to run N times (where N = number of workers). This causes duplicate fetches, duplicate rewrites, and duplicate LLM charges.

- The `web` container runs `gunicorn` only — no scheduler import, no `scheduler.start()` call anywhere in the Flask app factory or any module it imports at startup.
- The `scheduler` container imports and starts APScheduler in `app/scheduler.py` (the `__main__` module), which is a separate process that never handles HTTP requests.
- Do not add `scheduler.start()` to `create_app()` or any Flask init code, even for convenience during development.

---

## What This System Is Not

- Not a scraper. It uses RSS and official APIs.
- Not a republisher. Every article links to and credits the original source.
- Not a single-page application. There is no client-side routing.
- Not a local-only tool. It uses external LLM APIs (Anthropic, OpenAI, Gemini) — an internet connection and API key are required.
