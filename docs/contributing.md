# Contributing

Quorlo is pre-alpha, so early input has a lot of influence. The most useful contributions right now are real-world problems: messy schemas, cryptic codes, and the questions your agents get wrong. Share them in [Discussions](https://github.com/Quorlo/quorlo/discussions).

## Project conventions

[AGENTS.md](https://github.com/Quorlo/quorlo/blob/main/AGENTS.md) describes how Quorlo is built: principles, package layout, architecture and coding conventions. AI coding agents read it automatically; people should read it before their first change.

## Development setup

```bash
git clone https://github.com/Quorlo/quorlo.git
cd quorlo
uv sync --all-extras
uv run pytest                 # unit tests, no Docker needed
```

Integration tests run against the demo database:

```bash
docker compose up -d
QUORLO_TEST_DSN=postgresql://quorlo:quorlo@localhost:15432/quorlo_demo \
  uv run pytest -m integration
```

## Adding a check

A check is a class in `src/quorlo/readiness/checks/`, in the module for the question it answers. Subclass `BaseCheck` and declare:

- `id`, `dimension`, `scope`, `severity`, `description`, and optionally `weight`;
- `summary`: a short problem phrase for a line that groups many findings, e.g. `"no table description"`;
- `fix_hint`: one actionable line. `{table}` and `{column}` are filled in, e.g. `"COMMENT ON TABLE {table} IS '...';"`;
- `version`: bump it whenever a rule change can change the check's findings, so `quorlo diff` can tell a stricter check from worse data.

A class that leaves out a declaration, or uses another placeholder, fails when Quorlo is imported. A check that judges one table implements `run(table)`. A check that compares tables across the estate implements `start()`, returning an object that `observe()`s each table and reports `findings()` once at the end. Add it to `DEFAULT_CHECKS` and document it in `docs/reference/checks.md`.

## Working on these docs

```bash
uv run --group docs mkdocs serve      # live preview on http://127.0.0.1:8000
```

The pages live in `docs/`. They are published to GitHub Pages on every merge to `main`.

## Pull requests and sign-off

Every commit needs a [DCO](https://developercertificate.org/) sign-off (`git commit -s`), and `main` only accepts pull requests that pass CI. The full guide, including how to fix a missing sign-off, is in [CONTRIBUTING.md](https://github.com/Quorlo/quorlo/blob/main/CONTRIBUTING.md).
