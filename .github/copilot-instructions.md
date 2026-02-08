# Copilot Instructions (odds-value)

## Stack & layout
- Python 3.13+, managed with `uv` (`uv.lock` present)
- Typer CLI entrypoint: `odds-value` → `src/odds_value/cli/app.py`
- Settings via Pydantic (`src/odds_value/core/config.py`) loaded from `.env`
- SQLAlchemy ORM models in `src/odds_value/db/models/**` and repositories in `src/odds_value/db/repos/**`
- Alembic migrations under `alembic/` (env loads `.env` and imports `odds_value.db.models`)

## Dev workflow
- Formatting/linting is typically enforced via pre-commit hooks (see `.pre-commit-config.yaml`): `ruff --fix`, `ruff-format`, and `black`.
- When you do need to run checks manually, prefer `uv run`:
	- Lint: `uv run ruff check .`
	- Format: `uv run ruff format .`
	- Typecheck: `uv run mypy src` (strict)
	- Tests: `uv run pytest -q`
	- CLI: `uv run odds-value --help`

## Database (local-first)
- Default local DB is SQLite at `sqlite+pysqlite:///./odds_value.db` (override with `DATABASE_URL`)
- CLI DB sessions are created via `src/odds_value/cli/common.py:session_scope()`
- Prefer adding DB access in repositories (see `src/odds_value/db/repos/base.py:BaseRepository` using `select()`)

## Alembic workflow
- Upgrade: `uv run alembic upgrade head`
- New migration: `uv run alembic revision --autogenerate -m "..."`
- Model discovery relies on importing `odds_value.db.models` in `alembic/env.py`; ensure new models are imported in `src/odds_value/db/models/__init__.py`.

## Ingestion/provider conventions
- Provider adapters implement `ProviderAdapter.fetch_entities()` and return an `EntityBundle` (`src/odds_value/ingestion/providers/base/{adapter.py,types.py}`).
- Adapters are registered in an `AdapterRegistry` (`src/odds_value/ingestion/providers/base/registry.py`).
- Example: API-Sports registration reads `ProviderSport.base_url` from the DB (`src/odds_value/ingestion/providers/api_sports/provider.py`), then builds an `ApiSportsClient` and registers league-specific adapters.
- Seed required provider rows first: `uv run odds-value seed-provider-data seed-all` (`src/odds_value/cli/seed_provider_data.py`).

## Repo-specific guardrails
- Keep changes minimal and consistent with strict typing; avoid `Any` unless forced by external JSON.
- When touching provider HTTP code, use `BaseHttpClient.request_json()` for consistent error handling (`src/odds_value/ingestion/providers/base/client.py`).
