# AGENTS.md

Project context and conventions for anyone changing Quorlo: AI coding agents (Codex,
Cursor, Copilot, Claude Code and others) and human contributors alike. Read this first.

## What Quorlo is

Quorlo is an open-source tool that makes enterprise data AI-ready. It:

1. **Scans** data platforms (Databricks, Snowflake, Postgres, MySQL) read-only.
2. **Scores** how AI-ready each table and column is.
3. **Drafts** missing metadata (descriptions, code meanings, keys, PII tags).
4. **Routes** drafts to data owners for review.
5. **Writes back** approved metadata to the catalogs people already use
   (Unity Catalog, Snowflake comments and tags, dbt YAML, later DataHub and OpenMetadata).

Quorlo is **not a catalog** and must never become a system of record. It reads
metadata, produces reports and proposals, and pushes approved results to
existing systems.

Status: pre-alpha. Postgres is the first connector.

## The five questions

Readiness is measured against five questions. Every check belongs to exactly one,
via the `Dimension` enum in `quorlo.readiness`:

| Dimension | Question | What it needs |
| --- | --- | --- |
| `MEANING` | What is it? | Business descriptions, keys, meaning of codes |
| `CERTIFICATION` | Is it the right one? | One certified source per concept |
| `TRUST` | Can I trust it? | Freshness, quality results, known issues |
| `LINEAGE` | Where did it come from? | Lineage back to the source, across platforms |
| `GOVERNANCE` | Am I allowed to use it? | PII tags, ownership, access policy |

Scores are reported overall and per dimension, never only as one opaque number.

## Principles (non-negotiable)

- **Connectors are read-only for data.** Scanning never modifies anything.
  The Postgres connector enforces this at the driver (`conn.read_only = True`).
- **Write-back is metadata only**: comments, tags, descriptions. Never data.
- **Never read sample values unless the user explicitly enables it.** The metadata
  models have no field that can hold a sample value; keep it that way. Row counts
  come from catalog statistics, not `COUNT(*)`.
- **Humans approve.** Nothing is written to a catalog without a review step or an
  explicit confidence policy set by the user.
- **Pluggable model backends**: a decision model for classification, any LLM for
  text, local options when data can't leave the network. (Not built yet.)
- **Prefer existing standards** (OpenLineage, dbt YAML, Open Semantic Interchange)
  over inventing formats.
- **Secrets stay secret.** DSNs are `pydantic.SecretStr` so passwords can't leak
  through reprs, logs or tracebacks.

Prefer making a violation unrepresentable in the code over documenting a rule.

## Stack

- Python 3.11+, src layout, package `quorlo`, CLI command `quorlo`
- [uv](https://github.com/astral-sh/uv) for environments and dependencies
- ruff for lint and format, pytest for tests
- Typer for the CLI, Rich for terminal output, Pydantic v2 for data models
- psycopg 3 for Postgres

## Layout

```
src/quorlo/
  models.py          platform-neutral metadata models (Database > Schema > Table > Column)
  connectors/        everything a plugin author needs, re-exported from quorlo.connectors:
    base.py          Connector protocol (streaming), DatabaseInfo, FetchStats, read_database
    registry.py      discovery via the `quorlo.connectors` entry-point group
    postgres/        queries (SQL), runner (snapshot txn + query counting),
                     catalog (SchemaAssembler: rows -> models), types, connector
  readiness/         base (Finding, TableCheck, EstateCheck), engine (ReadinessEngine,
                     Assessment, FindingSink), checks/ (one module per question), names
  history/           runs over time, re-exported from quorlo.history:
    models.py        RunHeader, ScanRun, diff_runs (pure, no I/O)
    findings.py      FindingQuery, FindingGrouper: findings per check per table (pure)
    store/           RunStore protocol (base), schema history (migrations), SQLite backend
  scanner.py         Scanner: fetch -> check -> score -> save, streamed and timed
  stats.py           Phase, PhaseClock, ScanStats
  cli/               thin Typer commands, one module per group; app.py registers them all
  output/            views (ReportView, FindingsView, RunsView, DiffView, NextSteps) and
                     JSON; views render, they never compute
demo/                messy demo schema for the docker-compose Postgres
tests/               mirrors src/ (tests/connectors, tests/history); tests/integration/
                     needs a running database
```

## Architecture notes

- **Connectors are plugins.** `Connector` is a `runtime_checkable` `typing.Protocol`,
  not a base class, so third-party packages don't depend on core's class hierarchy.
  They register in the `quorlo.connectors` entry-point group. The built-in Postgres
  connector registers the same way, so core always exercises the plugin path.
- **Runs are compared by finding fingerprint** (check, table, column, key), never by
  message text. Bump a check's `version` whenever a rule change can change its findings.
- **Tests never touch the real run history**: `tests/conftest.py` points `QUORLO_STORE`
  at a temp file for every test.
- **Scans stream; nothing holds the whole estate.** A connector's `iter_schemas()`
  yields one complete schema at a time, fetched with a fixed number of queries per
  schema (Postgres: 3, plus 1 for the schema list) inside one read-only REPEATABLE READ
  snapshot. The `Scanner` passes each schema to the engine and the run writer, then
  drops it. Never add a per-table query; `test_postgres_batching.py` holds the count.
- **Every check declares a `summary` and a `fix_hint`** ({table}/{column} placeholders);
  `BaseCheck` rejects a check without them at import. `quorlo findings` is the one place
  findings are listed; `scan` and `runs show` show scores only.
- **Checks only report what is wrong.** A `TableCheck.run(table)` judges one table. An
  `EstateCheck` judges tables against the estate: `start()` returns a per-scan run that
  `observe()`s each table (keep a small signature, not the table) and reports once at the
  end. Check objects stay stateless. Findings go to a `FindingSink` (the run writer when
  saving), not into the report. Each check's pass rate is `1 - failed / units`, units
  from its `Scope`; scores are weight-averaged pass rates.

## Commands

```bash
uv sync --all-extras                 # set up the environment
uv run ruff check .                  # lint
uv run ruff format --check .         # format check (drop --check to fix)
uv run pytest                        # unit tests (no Docker needed)

docker compose up -d                 # demo Postgres on localhost:15432
QUORLO_TEST_DSN=postgresql://quorlo:quorlo@localhost:15432/quorlo_demo \
  uv run pytest -m integration       # integration tests
uv run quorlo scan --connector postgres \
  --dsn postgresql://quorlo:quorlo@localhost:15432/quorlo_demo
```

## Conventions

- **Follow OOP and clean-code practice; this is the project's strongest rule.** Small
  classes and functions with one job each, clear names, behaviour on the object that owns
  the data, collaborators behind Protocols, no god modules or long functions, no
  duplication. When touching code that breaks this, refactor it in its own commit.
- Run lint, format check and unit tests before every commit.
- Add user-visible changes to the `Unreleased` section of CHANGELOG.md (Keep a Changelog).
- Test file names must be unique across `tests/` (pytest imports them by basename).
- Every commit is signed off: `git commit -s` (DCO, see CONTRIBUTING.md).
- Small, focused commits. Conventional-style subjects: `feat(scope): ...`,
  `fix: ...`, `docs: ...`, `test: ...`, `build: ...`, `ci: ...`.
- Unit tests must run without Docker or network access.
- Tests that need a real database are marked `@pytest.mark.integration`, take their
  DSN from `QUORLO_TEST_DSN`, and skip when it is unset. Plain `pytest` excludes them.
- The demo Postgres listens on host port 15432. Not 5432, so it never collides with a
  developer's local Postgres, and below 49152, because Windows reserves ranges inside the
  dynamic port range (49152-65535) for Hyper-V and WSL, and Docker Desktop cannot publish them.
- Docs live in `docs/` (MkDocs Material, config in `mkdocs.yml`). Preview with
  `uv run --group docs mkdocs serve`; CI builds them with `--strict`, so broken links fail.
  Merges to `main` publish them to GitHub Pages. Update the docs when you change
  user-facing behavior, CLI options or checks.
