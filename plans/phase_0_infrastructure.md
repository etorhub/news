# Phase 0 — Infrastructure and Developer Experience

Implement Phase 0 of the MVP: Docker multi-service setup, Python tooling (Ruff, Mypy, Pytest), Alembic migrations with full schema, Lefthook git hooks, and Commitizen conventional commits. Includes a minimal Flask app skeleton so Docker can build and run.

Reference: [docs/MVP_PLAN.md](../docs/MVP_PLAN.md)

---

## Scope

1. **Dockerization** — multi-service compose (db, web, scheduler)
2. **Python tooling** — Ruff, Mypy, Pytest, Alembic
3. **Lefthook** — git hooks for lint, format, type check, test, commit message
4. **Commitizen** — conventional commits config and enforcement

---

## Deliverables

- `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `.env.example`
- `pyproject.toml` with Ruff, Mypy, Pytest, Commitizen config
- `lefthook.yml` with pre-commit and pre-push hooks
- `alembic/` with initial migration creating all tables
- Minimal Flask app skeleton (app factory, config, db connection, scheduler stub)

---

## Verification

1. `ruff check .` and `ruff format --check .` pass
2. `mypy .` passes
3. `pytest` passes
4. `docker compose up` starts all three services; web responds on `:5000/health`
5. `lefthook install`; `cz check` rejects non-conventional commit messages
