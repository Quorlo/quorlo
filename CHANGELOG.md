# Changelog

All notable changes to Quorlo are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and Quorlo will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it has a first release.

## [Unreleased]

### Added

- Read-only Postgres scan that scores how AI-ready each table is, overall and for four
  of the five readiness questions: meaning, certification, trust and governance.
- Checks: missing table and column descriptions, missing primary keys, cryptic column
  names, near-duplicate tables, missing freshness columns, and personal data not marked
  as PII.
- `quorlo scan`, `quorlo connectors` and `quorlo version`, with `--format json`.
- Run history in a local SQLite file: every scan is saved and compared with the previous
  one. `quorlo runs`, `quorlo runs show` and `quorlo diff` list, reprint and compare runs.
- Scan timing: total time, time per phase, queries issued, and schemas, tables and
  columns scanned.
- Connector plugin contract (`quorlo.connectors`), discovered through the
  `quorlo.connectors` entry-point group.
- Demo database (`docker compose up -d`) with a deliberately messy retail schema.
- Documentation site at https://quorlo.github.io/quorlo/.
