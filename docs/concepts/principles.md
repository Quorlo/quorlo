# Principles

Quorlo connects to production data platforms, so what it will *not* do matters as much as what it does. Where possible, these principles are enforced by the shape of the code rather than by convention.

## Data stays put

Quorlo reads metadata and writes metadata back. It does not copy data out.

- The metadata models have **no field that can hold a sample value**, and they reject unknown fields. Scanned metadata cannot carry data, even by accident.
- Row counts come from **catalog statistics** (in Postgres, `pg_class.reltuples`), never from `COUNT(*)`.
- Sample values will only ever be read when a user explicitly enables it.

## Connectors are read-only for data

Scanning never modifies anything. The Postgres connector opens its connection with `read_only = True`, so every transaction is `READ ONLY` and the **server** rejects writes, not just Quorlo's own queries. It refuses to run on a connection configured for writing.

Write-back, when it arrives, is limited to metadata: comments, tags and descriptions. Never data.

## Humans approve

Nothing is written to a catalog without a review step or an explicit confidence policy set by the user.

## Secrets stay secret

Connection strings are held as `pydantic.SecretStr`, so a password in a DSN never appears in a log line, repr or traceback. Connection errors are reported without the password.

## No lock-in

Every model backend will be pluggable: a fast decision model for classification, any LLM or native generator for text, and local options when data can't leave your network.

## Interoperate

Quorlo prefers existing standards, such as OpenLineage, dbt YAML and Open Semantic Interchange, over new formats. It is not a catalog and never becomes a system of record.
