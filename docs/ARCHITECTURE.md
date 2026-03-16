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

- `schema.py` — table definitions and migrations
- `articles.py` — read/write for articles
- `rewrites.py` — read/write for rewrite cache
- `users.py` — read/write for users and profiles
- `connection.py` — connection pool management

### `app/routes/`

Flask blueprints. Routes are thin wrappers: parse request, call service, return template.

- `reader.py` — main reader interface (`/`, `/articles/<id>/expand`)
- `auth.py` — login, register, logout
- `setup.py` — initial configuration wizard (`GET /setup`, `POST /setup`)
- `settings.py` — configuration interface; allows editing profile fields after initial setup

### `app/templates/`

Jinja2 templates. Pages extend `base.html`. HTMX responses use partials.

```
templates/
├── base.html               # Shell: nav, font settings, TTS controls
├── index.html              # Main reader view (today's digest)
├── login.html              # Login page
├── register.html           # Registration page
├── setup.html              # Initial configuration wizard
├── settings.html           # Settings page
└── partials/
    ├── article_card.html   # Summary card (one article in list)
    ├── article_expanded.html  # Full simplified article
    ├── article_list.html   # The full list of today's articles
    ├── setup_sources.html  # Source selection section for setup
    └── setup_topics.html   # Topic selection section for setup
```

### `app/tts/`

Thin helpers for browser TTS. The actual synthesis happens via the Web Speech API in the browser — no server-side audio generation. If the browser does not support the Web Speech API, TTS controls are hidden via feature detection.

- `helpers.py` — prepares text for TTS (sentence splitting, SSML markers if needed)

---

## Database Schema

PostgreSQL 16. Multi-user from the start.

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
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
```

### Profile hash

The cache key for a rewrite is `sha256(json(profile_rewrite_fields))`. The hash includes **only fields that affect the rewrite output**:

- `language`
- `rewrite_tone`
- `filter_negative`

It does **not** include source selections, topic selections, or location. Changing which sources you follow does not invalidate existing rewrites. Two users with identical language, tone, and filter settings share cached rewrites.

---

## Configuration

All config lives in `config/`. The app reads it at startup. No config is hardcoded.

### `config/app.yaml`

```yaml
llm:
  provider: anthropic        # anthropic | openai | gemini
  model: claude-sonnet-4-20250514

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
  secret_key: ${SECRET_KEY}
```

### `config/sources.yaml`

Defines the catalog of available sources and their metadata. Each source should include a `topics` list. User selections are stored in PostgreSQL via the setup wizard and settings page.

```yaml
sources:
  - id: "3cat"
    name: "3Cat Notícies"
    type: rss
    url: "https://www.ccma.cat/rss/noticia/catala/rss.xml"
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

When `filter_negative` is enabled, the prompt includes an additional instruction to omit or soften distressing content.

### Rewrite scheduling

The daily rewrite job (APScheduler):

1. Collects all active users and their profile hashes
2. Collects today's articles (from scheduled fetch)
3. For each unique profile hash, rewrites articles that don't have a cached result
4. Stores results in the `rewrites` table

Two users with the same profile hash share cached rewrites — the LLM is never called twice for the same content + profile combination.

---

## What This System Is Not

- Not a scraper. It uses RSS and official APIs.
- Not a republisher. Every article links to and credits the original source.
- Not a single-page application. There is no client-side routing.
- Not a local-only tool. It uses external LLM APIs (Anthropic, OpenAI, Gemini) — an internet connection and API key are required.
