# Admin Dashboard

The admin dashboard provides operators with visibility into ingestion pipelines, job history, user activity, and system health. It is intended for the person who deploys and maintains the instance — not for end users or caregivers.

---

## Access

- **URL:** `/admin`
- **Requirement:** You must be logged in and have `is_admin = true` on your user account.
- **Non-admins:** Accessing `/admin` without admin privileges returns HTTP 403.

### Granting admin access

Admin status is not granted automatically. Use the CLI to promote a user:

```bash
flask make-admin user@example.com
```

This sets `is_admin = true` for the user with that email. The user must already exist (have registered).

---

## Dashboard sections

### Articles & clusters

A dedicated page at `/admin/articles` lets operators browse:

- **Articles view** — Paginated table of all fetched and enriched articles with extraction status, source, fetched date, and cluster assignment. Filters: extraction status (pending, extracted, failed, skipped), source.
- **Clusters view** — Paginated list of clusters with article count and sample titles. Each cluster can be expanded to show its member articles.

### 1. Overview

Four stat cards:

- **Users** — Total and active user counts
- **Articles today** — Articles fetched in the current day
- **Active feeds** — Active vs. total feed count
- **Last job run** — Most recent scheduled job name and timestamp

### 2. Scheduled jobs

Table of recent job runs from the `job_runs` table:

- Job name (`fetch_feeds`, `enrich_articles`, `cluster_articles`, `rewrite_articles`)
- Started at
- Duration
- Status (success, error, running)
- Result summary (e.g. articles inserted, clusters created)

The jobs panel auto-refreshes every 60 seconds via HTMX.

### 3. Feed health

Table of all feeds with source info:

- Source name
- Feed URL
- Active/inactive
- Consecutive failures
- Last fetched timestamp

Rows with inactive feeds or non-zero failures are highlighted.

### 4. Article pipeline

- **Status breakdown** — Counts by `extraction_status`: pending, extracted, failed, skipped
- **Last 7 days** — Articles fetched per day

### 5. Clustering & rewrites

- Total clusters
- Articles in clusters vs. with embeddings
- Clusters with at least one successful rewrite
- Rewrite failures in the last 24 hours

### 6. Users

Read-only table of all users:

- Email
- Joined date
- Last login
- Active
- Admin

### 7. Incidents

Auto-computed list shown prominently when non-empty:

- **Feed deactivated** — Feeds turned off by the circuit breaker (consecutive failures ≥ threshold)
- **Extraction backlog** — Articles stuck in `pending` for more than 2 hours
- **Rewrite failures** — Cluster rewrites that failed in the last 24 hours
- **Job errors** — Scheduled jobs that exited with `status = 'error'` in the last 24 hours

---

## Job run persistence

The scheduler records each job execution in the `job_runs` table:

1. Before running: insert a row with `status = 'running'`
2. On success: update with `status = 'success'`, `result` (JSONB of the report)
3. On exception: update with `status = 'error'`, `error_message`

Report structures vary by job:

| Job | Result keys |
|-----|-------------|
| `fetch_feeds` | `feeds_checked`, `feeds_fetched`, `articles_inserted`, `feeds_deactivated` |
| `enrich_articles` | `articles_checked`, `articles_extracted`, `articles_failed`, `articles_skipped` |
| `cluster_articles` | `articles_embedded`, `articles_clustered`, `clusters_created` |
| `rewrite_articles` | `profiles_processed`, `clusters_attempted`, `clusters_succeeded`, `clusters_failed` |

---

## Database tables

### `job_runs`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `job_name` | TEXT | `fetch_feeds`, `enrich_articles`, `cluster_articles`, `rewrite_articles` |
| `started_at` | TIMESTAMPTZ | When the job started |
| `finished_at` | TIMESTAMPTZ | When the job finished (null if still running) |
| `duration_ms` | INTEGER | Duration in milliseconds |
| `status` | TEXT | `running`, `success`, `error` |
| `result` | JSONB | Report data (varies by job) |
| `error_message` | TEXT | Error message when `status = 'error'` |

### `users` (admin columns)

| Column | Type | Description |
|--------|------|-------------|
| `is_admin` | BOOLEAN | Whether the user can access `/admin` |
| `last_login_at` | TIMESTAMPTZ | Last successful login |

---

## CLI commands

| Command | Description |
|---------|-------------|
| `flask make-admin <email>` | Grant admin privileges to a user |

---

## Implementation notes

- **Blueprint:** `app/routes/admin.py` — `admin_bp` at `/admin`
- **DB layer:** `app/db/admin.py` — overview stats, job run CRUD, feed health, pipeline stats, clustering stats, user list, incidents, admin articles/clusters queries
- **Templates:** `templates/admin/dashboard.html`, `templates/admin/articles.html`, `templates/admin/partials/jobs.html`, `templates/admin/partials/articles_table.html`, `templates/admin/partials/clusters_list.html`, `templates/admin/partials/cluster_detail.html`
- **Guard:** `admin_bp.before_request` checks `session["user_id"]` and `users.is_admin`; aborts with 403 if not admin
