# Quorlo

**Make your data AI-ready.** Quorlo scans Databricks, Snowflake, Postgres and MySQL, scores how ready each table is for AI agents, drafts the missing metadata, and writes what your data owners approve back to the catalogs you already use.

> **Status: pre-alpha.** We are designing the scanner and readiness model. Nothing is installable yet. Ideas, use cases and design feedback are very welcome in [Discussions](https://github.com/Quorlo/quorlo/discussions).

## Why

AI agents rarely fail on the model. They fail on data they can't understand or trust. The table exists, but nobody wrote down what `status = 4` means, which of three revenue tables is the right one, or whether it's fresh.

Catalogs can hold these answers, but most fields stay empty because nobody has time to write metadata by hand. Quorlo makes that metadata cheap to produce and keep current.

## The five questions

A table is AI-ready when an agent can answer these without asking a human:

| Question | What it needs |
| --- | --- |
| What is it? | Business descriptions, keys, meaning of codes |
| Is it the right one? | One certified source per concept |
| Can I trust it? | Freshness, quality results, known issues |
| Where did it come from? | Lineage back to the source, across platforms |
| Am I allowed to use it? | PII tags, ownership, access policy |

Quorlo scores every table and column against these questions and tells you where the biggest gaps are.

## How it works

1. **Scan.** Connect read-only to your platforms and score readiness per table and column.
2. **Enrich.** Draft descriptions, code meanings, keys and PII tags from schema, samples, query logs and dbt code.
3. **Review.** High-confidence results can be auto-accepted; uncertain ones go to the data owner to approve, edit or reject.
4. **Write back.** Approved metadata lands where it belongs: Unity Catalog, Snowflake comments and tags, dbt YAML, and later DataHub and OpenMetadata.

Quorlo is not a catalog. It never becomes another system of record.

## What makes it different

Databricks, Snowflake, DataHub and Collate can already generate descriptions inside their own platforms. Quorlo treats those generators as interchangeable backends and focuses on what they don't do:

- **Cross-platform readiness** for Databricks, Snowflake and operational databases in one view
- **Confidence-based review**, so owners only look at the doubtful cases
- **Certified source selection** among similar tables
- **Fully open source and self-hosted**, end to end
- **Pluggable models:** a fast decision model for classification, any LLM or native generator for text, and local options when data can't leave your network

## Planned support

| Platform | Scan | Write-back |
| --- | --- | --- |
| Postgres | MVP | n/a (reports only) |
| MySQL | MVP | n/a (reports only) |
| Snowflake | MVP | Comments and tags |
| Databricks (Unity Catalog) | MVP | Comments and tags |
| dbt | MVP (as context) | YAML via pull request |
| DataHub, OpenMetadata | Later | Later |

## Roadmap

1. **Scan and enrich (MVP):** connectors, readiness score, drafted metadata, review, write-back
2. **Catalog integrations:** DataHub and OpenMetadata; read results from dbt tests, Great Expectations and Soda
3. **Cross-platform lineage** with OpenLineage
4. **Semantic export** to dbt MetricFlow and Open Semantic Interchange
5. **Continuous readiness:** CI and scheduled runs, drift detection
6. **Agent serving:** certified data over MCP with access policies and audit

## Contributing

We're early, so the most useful contributions right now are real-world problems: messy schemas, cryptic codes, and the questions your agents get wrong. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache 2.0](LICENSE)
