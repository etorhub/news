# ARCHITECTURE.md

Technical reference for the Accessible News Aggregator. This document describes the system as it is built, not as it is planned. Update it when architectural decisions change.

---

## System Overview

A Flask web application that fetches news from RSS feeds and open publisher APIs, rewrites each article via a local LLM to match a reader's accessibility profile, and presents the result in a clean, accessible reader interface.

The system has no client-side rendering. Flask renders all HTML server-side via Jinja2. HTMX makes targeted requests to Flask routes and swaps HTML fragments into the page. SQLite stores fetched articles, rewritten content, and the user profile.

---

## Request Lifecycle

### First-time setup

```
User opens app for the first time
    → GET /
    → Flask checks SQLite: does a user profile exist?
    → No: redirect to GET /setup
    → Caregiver fills in: location, language, sources, topics, negative news filter, rewrite tone
    → POST /setup → validate, store in SQLite → redirect to /
```

### First open of the day

```
User opens browser
    → GET /
    → Flask checks SQLite: has today's content been processed?
    → No: return skeleton page with HTMX polling target
    → HTMX polls GET /articles/status
    → Flask triggers background processing (fetch + rewrite pipeline)
    → Articles are processed one at a time, written to SQLite as they complete
    → Each poll returns a count: "3 of 5 articles ready"
    → When complete, HTMX swaps in the article list
    → User sees the first article immediately
```

### Subsequent opens (same day)

```
User opens browser
    → GET /
    → Flask checks SQLite: content already processed today
    → Returns full article list immediately — no LLM calls made
```

### Article expansion

```
User taps "Read more"
    → hx-post="/articles/{id}/expand"
    → Flask checks SQLite: has full rewrite been cached?
    → Yes: return partials/article_expanded.html with cached content
    → No: call LLM, cache result, return partial
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

A `RawArticle` has: `id`, `title`, `url`, `source`, `published_at`, `raw_text` (may be partial for paywalled sources), `full_text` (populated when full content is available).

### `app/llm/`

The LLM abstraction layer. Nothing outside this directory calls an LLM SDK directly.

- `provider.py` — `LLMProvider` abstract base class and provider factory
- `providers/ollama.py` — Ollama implementation
- `providers/openai.py` — OpenAI implementation (fallback)
- `providers/anthropic.py` — Anthropic implementation (fallback)
- `prompts/` — prompt template files (`.txt`)
- `rewriter.py` — orchestrates the rewrite: loads profile, builds prompt, calls provider, returns `RewrittenArticle`

### `app/db/`

All SQLite access. No other module writes to the database directly.

- `schema.py` — table definitions and migrations
- `articles.py` — read/write for articles and rewrites
- `profile.py` — read/write for the user profile
- `cache.py` — rewrite cache logic (check, store, invalidate)

Schema:

```sql
articles (
    id TEXT PRIMARY KEY,
    title TEXT,
    url TEXT,
    source TEXT,
    published_at TEXT,
    raw_text TEXT,
    fetched_at TEXT
)

rewrites (
    article_id TEXT,
    profile_hash TEXT,
    summary TEXT,
    full_text TEXT,
    rewrite_failed INTEGER DEFAULT 0,
    created_at TEXT,
    PRIMARY KEY (article_id, profile_hash)
)

user_profile (
    id INTEGER PRIMARY KEY DEFAULT 1,
    location TEXT,
    language TEXT NOT NULL DEFAULT 'ca',
    filter_negative INTEGER NOT NULL DEFAULT 0,
    rewrite_tone TEXT NOT NULL DEFAULT 'Short sentences. Simple vocabulary. No jargon.',
    created_at TEXT,
    updated_at TEXT
)

user_sources (
    source_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1
)

user_topics (
    topic_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1
)
```

### `app/routes/`

Flask blueprints. Routes are thin wrappers: parse request, call service, return template.

- `reader.py` — main reader interface (`/`, `/articles/status`, `/articles/<id>/expand`)
- `setup.py` — initial configuration wizard (`GET /setup`, `POST /setup`)
- `settings.py` — caregiver configuration interface; allows editing the same fields after initial setup
- `tts.py` — TTS support routes if needed server-side

### `app/templates/`

Jinja2 templates. Pages extend `base.html`. HTMX responses use partials.

```
templates/
├── base.html               # Shell: nav, font settings, TTS controls
├── index.html              # Main reader view
├── setup.html              # Initial configuration wizard
├── settings.html           # Caregiver settings page
└── partials/
    ├── article_card.html   # Summary card (one article in list)
    ├── article_expanded.html  # Full simplified article
    ├── article_list.html   # The full list of today's articles
    ├── loading.html        # Polling state while processing
    ├── setup_sources.html  # Source selection section for setup
    └── setup_topics.html   # Topic selection section for setup
```

### `app/tts/`

Thin helpers for browser TTS. The actual synthesis happens via the Web Speech API in the browser — no server-side audio generation.

- `helpers.py` — prepares text for TTS (sentence splitting, SSML markers if needed)

---

## Configuration

All config lives in `config/`. The app reads it at startup. No config is hardcoded.

### `config/app.yaml`

```yaml
llm:
  provider: ollama          # ollama | openai | anthropic
  model: llama3.2
  base_url: http://ollama:11434  # Docker service name

processing:
  articles_per_day: 5
  summary_sentences: 3

server:
  port: 5000
  debug: false
```

### `config/sources.yaml`

Defines the catalog of available sources and their metadata. Each source should include a `topics` list. User selections are stored in SQLite via the setup wizard and settings page.

```yaml
sources:
  - name: "3Cat Notícies"
    type: rss
    url: "https://www.ccma.cat/rss/noticia/catala/rss.xml"
    language: ca
    full_text: true

  - name: "El Crític"
    type: rss
    url: "https://www.elcritic.cat/feed"
    language: ca
    full_text: true

  - name: "The Guardian"
    type: api
    api: guardian
    topics: ["world", "science"]
    language: en
    full_text: true
```

---

## Docker Setup

Two services: the Flask app and Ollama.

```yaml
# docker-compose.yml (simplified)
services:
  app:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./config:/app/config
      - ./data:/app/data      # SQLite lives here
    depends_on:
      - ollama

  ollama:
    image: ollama/ollama
    volumes:
      - ollama_data:/root/.ollama
```

The SQLite database and Ollama models persist across restarts via named volumes.

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

### Profile hash

The cache key for a rewrite is `sha256(article_id + json(profile))`. The profile includes `location`, `language`, `filter_negative`, `rewrite_tone`, and selected source/topic IDs. If any of these change, cached rewrites for that day are invalidated.

---

## What This System Is Not

- Not a scraper. It uses RSS and official APIs.
- Not a republisher. Every article links to and credits the original source.
- Not a single-page application. There is no client-side routing.
- Not multi-tenant (yet). One profile, one user, one SQLite file. User preferences live in SQLite, not in YAML.
