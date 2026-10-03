# Contributing to Quorlo

Thanks for your interest. Quorlo is pre-alpha, so the shape of the project is still open and early input has a lot of influence.

## Ways to help right now

- **Share a real problem.** Open a [Discussion](https://github.com/Quorlo/quorlo/discussions) describing data your agents struggle with: cryptic column names, undocumented codes, duplicate tables, missing lineage. Anonymized examples are gold.
- **Review the design.** Comment on design proposals and the readiness model as they're posted.
- **Report issues.** Once code lands, open an issue for bugs or unclear behavior, with steps to reproduce.
- **Add a connector.** Connectors are plugins, so new platforms can be added without touching the core. Please open a Discussion first so we can agree on scope.

## Project conventions

[AGENTS.md](AGENTS.md) describes how Quorlo is built: its principles, package layout, architecture and coding conventions. It's written for AI coding agents and people alike, so read it before your first change.

## Development setup

Quorlo is written in Python.

Requirements:

- Python 3.11 or newer
- [uv](https://github.com/astral-sh/uv) for environments and dependencies
- Docker, for the demo database and integration tests

```bash
git clone https://github.com/Quorlo/quorlo.git
cd quorlo
uv sync --all-extras
uv run pytest
```

Setup details will change while the project takes shape; the README will always have the current quickstart.

## Pull requests

1. Open or comment on an issue first for anything beyond a small fix, so we agree on the approach.
2. Keep pull requests focused: one change per PR.
3. Add or update tests for behavior changes.
4. Run the checks locally before pushing:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest
   ```

5. Update docs when you change user-facing behavior.

### Commit sign-off

We use the [Developer Certificate of Origin](https://developercertificate.org/) instead of a CLA. Sign off each commit to confirm you have the right to submit it:

```bash
git commit -s -m "Add MySQL connector"
```

This adds a `Signed-off-by: Your Name <you@example.com>` line using your `user.name` and `user.email` from git config. That email must match the commit author, or the DCO check will fail.

A DCO check runs on every pull request. If it fails because a commit is missing a sign-off, fix it like this:

```bash
# Sign off the last commit
git commit --amend --signoff --no-edit

# Or sign off every commit in your branch
git rebase --signoff main

# Then update the pull request
git push --force-with-lease
```

Tip: to avoid forgetting, set an alias and use `git cs` instead of `git commit`:

```bash
git config --global alias.cs "commit -s"
```

Commits made in the GitHub web editor are signed off automatically.

## Writing a connector

A connector lets Quorlo read metadata from a platform, and optionally write approved metadata back. A good connector:

- Uses read-only credentials for scanning
- Reads schema, comments, tags and, where allowed, sample values and query history
- Never reads sample values unless the user enables it
- Implements write-back only for metadata (comments, tags, descriptions), never data
- Ships with tests against a local or containerized instance where possible

The connector interface will be documented once the first connectors land.

## Principles

- **Data stays put.** Quorlo reads metadata and writes metadata back. It does not copy data out.
- **Humans approve.** Nothing is written to a catalog without a review step or an explicit confidence policy set by the user.
- **No lock-in.** Every model backend is pluggable, including local options.
- **Interoperate.** Prefer existing standards (OpenLineage, dbt YAML, Open Semantic Interchange) over new formats.

## Security

Please don't report security issues in public issues. Use GitHub's private vulnerability reporting on this repository instead.

## Code of conduct

Be respectful and constructive. We'll adopt the [Contributor Covenant](https://www.contributor-covenant.org/) as the project grows.

## License

By contributing, you agree that your contributions are licensed under the [Apache 2.0 License](LICENSE).
