# MVP Plan — Accessible News Aggregator

Canonical phased plan for the minimum viable product. This document replaces scattered MVP mentions elsewhere.

---

## MVP Scope Summary

| Phase | Deliverable           | Outcome                                                            |
| ----- | --------------------- | ------------------------------------------------------------------ |
| 1     | News source discovery | Populated catalog of validated feeds                               |
| 2     | Fetching pipeline     | Articles stored with metadata + full text when available           |
| 3     | Processing & storage  | LLM rewrites (3-line summary + full simplified) cached per profile |
| 4     | Platform              | Auth, profile config, feed UI, daily digest                        |

---

## Phase 1 — News Source Discovery

**Goal:** Obtain a catalog of news sources for the target region via automated discovery.

**Reference:** `agents/news_source_discovery_agent.md`

### Tasks

1. **Implement discovery pipeline** (or run as AI-assisted script)
   - Phase 1: Query reference databases (NewsAPI, ABYZ, GDELT, W3Newspapers)
   - Phase 2: Search-based discovery for digital-native outlets
   - Phase 3 (optional for MVP): TLD scan for `full` depth only
   - Phase 4: Validate each candidate (DNS, robots.txt, ToS, feed availability)

2. **Feed detection per source**
   - Try API → RSS/Atom → Google News RSS fallback
   - Store feed URL, type, poll interval in `source_feeds`

3. **Quality scoring**
   - Compute 0–100 score (editorial reputation, frequency, feed completeness, etc.)
   - Use for display ranking and ingestion priority

4. **Output**
   - Populate `news_sources` and `source_feeds` tables (SQLite-compatible schema)
   - For MVP: start with `quick` or `standard` depth for one region (e.g. Catalonia)
   - Initial priority: Open Catalan/Spanish publishers (RTVE, CCMA/3Cat, Vilaweb, El Crític, NacióDigital) — can be seeded manually if discovery is deferred

### MVP Simplifications

- Single region/language for first release (e.g. Catalonia, `ca`/`es`)
- Discovery can run as a one-time or periodic CLI/script; not required to be embedded in the web app
- If discovery is deferred: seed `config/sources.yaml` manually with 5–10 known open publishers

---

## Phase 2 — Fetching Pipeline

**Goal:** Programmatically fetch news from all configured sources on a schedule.

### Tasks

1. **Scheduled fetcher**
   - APScheduler jobs: poll feeds per `poll_interval_minutes` (or tiered: high/medium/low frequency)
   - Respect rate limits, `If-None-Match` / `If-Modified-Since` for conditional GET
   - Parse RSS/Atom via `feedparser`; normalise to `RawArticle` schema

2. **Full-text extraction**
   - Prefer full content from RSS when available (open publishers)
   - Fallback: RSS description/lede only (no paywall bypass)
   - Store `raw_text` and `full_text` (or equivalent) in `articles` table

3. **Deduplication**
   - Match on `guid` or `(source_id, url)` before insert
   - Update `last_item_guid` / `last_fetched_at` on `source_feeds`

4. **Failure handling**
   - Circuit breaker: after N consecutive failures, mark feed inactive
   - Log to `source_discovery_log` or equivalent for monitoring

### Output

- `articles` table populated with: `id`, `title`, `url`, `source_id`, `published_at`, `raw_text`, `full_text` (when available), `fetched_at`

---

## Phase 3 — Processing & Storage

**Goal:** Rewrite articles via LLM per user profile, cache results.

### Tasks

1. **LLM rewriter**
   - Load user profile (language, rewrite_tone, filter_negative)
   - Build prompt from `llm/prompts/` template
   - Output: 3-line summary + full simplified article
   - Store in `rewrites` keyed by `(article_id, profile_hash)`

2. **Processing trigger**
   - On first open of the day: fetch + rewrite pipeline
   - Process articles one at a time (or batched per config)
   - HTMX polling for progress: "3 of 5 articles ready"
   - Cache in SQLite; no re-processing on subsequent opens

3. **Profile hash**
   - Cache invalidation when profile changes (location, language, sources, topics, negative filter, rewrite tone)

4. **Daily digest**
   - "5 things today" (or configurable): select top N articles for the day
   - Process digest on first open; store in digest table or derived from articles + rewrites

### Output

- `rewrites` table with `summary`, `full_text` per article per profile
- Digest view or table for the day’s curated list

---

## Phase 4 — Platform

**Goal:** Web app with user accounts, configuration, and accessible feed UI.

End users and caregivers always access the platform, never the codebase. Flow: **create account → configuration page → see content**.

### Tasks

1. **Authentication**
   - User account creation (email + password, or equivalent)
   - Both end user and caregiver access the platform with the same account
   - Session-based; no OAuth for MVP
   - Unauthenticated users redirect to login

2. **Profile configuration**
   - Configuration page (after signup or first login): location, language, sources (all selected by default), topics (all selected), negative news filter, rewrite tone
   - Settings page: same fields, editable anytime
   - Stored in SQLite: `user_profile`, `user_sources`, `user_topics`

3. **Initial feed**
   - Main view: list of today’s articles (from digest or full set)
   - 3-line summary per article, expandable to full simplified text on tap
   - One-article-at-a-time mode (no infinite scroll)
   - Large touch targets, high contrast, large font

4. **Daily digest**
   - "5 things today" as the default view when opening the app
   - Optional: soft notification "You have 5 new articles" (browser notification or in-app badge)

5. **UI requirements**
   - Clean, ad-free
   - No clutter; minimal visual noise
   - Link to original source on every article

### Accessibility (non-negotiable)

- Large font, high contrast mode
- Large touch targets throughout
- Text-to-speech per article (browser Web Speech API)
- Configurable detail level: headline → summary → full simplified article

---

## What the MVP Includes

| Component                                               | Status |
| ------------------------------------------------------- | ------ |
| News source discovery (agent or manual seed)            | ✅     |
| Scheduled fetching from all sources                     | ✅     |
| Processing & storage (LLM rewrite, cache)               | ✅     |
| Authentication (user account creation)                  | ✅     |
| Profile configuration (setup wizard + settings)         | ✅     |
| Initial feed (3-line summary, expandable)               | ✅     |
| Daily digest ("5 things today")                         | ✅     |
| Clean, ad-free UI                                       | ✅     |
| Accessibility (large fonts, TTS, one-article-at-a-time) | ✅     |

---

## What the MVP Excludes (for now)

- Multi-user / multi-tenant (multiple accounts per deployment)
- OAuth or social login
- Paywalled content bypass
- Native mobile app
- Social or sharing features

---

## Suggested Implementation Order

1. **Phase 1** — Discovery or manual seed → `news_sources` + `source_feeds` (or `sources.yaml`)
2. **Phase 2** — Fetcher + scheduler → `articles` populated
3. **Phase 4 (partial)** — Auth, setup wizard, profile storage (no feed yet)
4. **Phase 3** — LLM rewriter + processing pipeline
5. **Phase 4 (complete)** — Feed UI, digest, expandable articles, TTS

---

## Database Schema Alignment

The discovery agent doc defines `news_sources`, `source_feeds`, `source_discovery_log`. Adapt for SQLite:

- Use `TEXT` for UUIDs or `INTEGER PRIMARY KEY`
- Use `JSON` or `TEXT` for arrays (e.g. `languages`)
- Ensure `articles` table links to `source_id` from `news_sources`

The existing `app/db` schema (`articles`, `rewrites`, `user_profile`, etc.) should be extended to reference `news_sources` when discovery is used, or kept separate if using `sources.yaml` only for MVP.

---

## Should the MVP Include Something Else?

**Consider adding:**

- **Soft daily notification** — "You have 5 new articles" (browser notification or in-app badge). Low effort, high value for reminding the user to check the digest.
- **High-contrast / dark mode toggle** — Already implied by "high contrast mode" in accessibility; ensure it's in the profile so the user (or caregiver) can set it once.

**Consider deferring:**

- **Caregiver remote config** — Both access the platform; the caregiver can configure from any device by logging in. No separate feature needed.
- **Multi-language source mixing** — Start with one language (e.g. Catalan); add language selection later.

**Already covered:** TTS, one-article-at-a-time, negative news filter, rewrite tone — all are core to the target user and should stay in MVP.

---

## Success Criteria

- User or caregiver creates an account, completes the configuration page, and sees a feed of 5 rewritten articles
- End user can open the platform, read 3-line summaries, expand to full content, use TTS
- No ads, no clutter, every article links to original source
- Processing is on-demand: first open of the day triggers fetch + rewrite; subsequent opens use cache
