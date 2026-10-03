# Contributing

Quorlo is pre-alpha, so early input has a lot of influence. The most useful contributions right now are real-world problems: messy schemas, cryptic codes, and the questions your agents get wrong. Share them in [Discussions](https://github.com/Quorlo/quorlo/discussions).

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

## Working on these docs

```bash
uv run --group docs mkdocs serve      # live preview on http://127.0.0.1:8000
```

The pages live in `docs/`. They are published to GitHub Pages on every merge to `main`.

## Pull requests and sign-off

Every commit needs a [DCO](https://developercertificate.org/) sign-off (`git commit -s`), and `main` only accepts pull requests that pass CI. The full guide, including how to fix a missing sign-off, is in [CONTRIBUTING.md](https://github.com/Quorlo/quorlo/blob/main/CONTRIBUTING.md).
