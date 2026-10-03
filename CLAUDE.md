# CLAUDE.md

Context for Claude Code sessions working in this repository. Read this first.

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
  connector.py       Connector protocol, ConnectionConfig, ConnectorCapabilities
  registry.py        connector discovery via the `quorlo.connectors` entry-point group
  readiness/         Check protocol, Dimension, Finding, scoring engine, built-in checks
  connectors/        built-in connectors (postgres)
  cli.py, render.py  Typer CLI and output rendering
demo/                messy demo schema for the docker-compose Postgres
tests/               unit tests; tests/integration/ needs a running database
```

## Architecture notes

- **Connectors are plugins.** `Connector` is a `runtime_checkable` `typing.Protocol`,
  not a base class, so third-party packages don't depend on core's class hierarchy.
  They register in the `quorlo.connectors` entry-point group. The built-in Postgres
  connector registers the same way, so core always exercises the plugin path.
- **Checks only report what is wrong.** `Check.run(table)` yields `Finding`s. The
  engine derives the denominator from the check's `Scope` (1 unit per table for
  TABLE checks, 1 per column for COLUMN checks):
  `score = 1 - weighted_findings / weighted_possible`.

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

- Run lint, format check and unit tests before every commit.
- Every commit is signed off: `git commit -s` (DCO, see CONTRIBUTING.md).
- Small, focused commits. Conventional-style subjects: `feat(scope): ...`,
  `fix: ...`, `docs: ...`, `test: ...`, `build: ...`, `ci: ...`.
- Unit tests must run without Docker or network access.
- Tests that need a real database are marked `@pytest.mark.integration`, take their
  DSN from `QUORLO_TEST_DSN`, and skip when it is unset. Plain `pytest` excludes them.
- The demo Postgres listens on host port 15432. Not 5432, so it never collides with a
  developer's local Postgres, and below 49152, because Windows reserves ranges inside the
  dynamic port range (49152-65535) for Hyper-V and WSL, and Docker Desktop cannot publish them.
