# Quorlo

**Make your data AI-ready.** Quorlo scans Databricks, Snowflake, Postgres and MySQL, scores how ready each table is for AI agents, drafts the missing metadata, and writes what your data owners approve back to the catalogs you already use.

**Documentation:** https://quorlo.github.io/quorlo/

> **Status: pre-alpha.** The first slice works: a read-only Postgres scan that scores four of the five readiness questions. Enrichment, review and write-back are still being designed, and nothing is published to PyPI yet. Ideas, use cases and design feedback are very welcome in [Discussions](https://github.com/Quorlo/quorlo/discussions).

## Quickstart

Scan the bundled demo database, a deliberately messy retail schema. You need [uv](https://github.com/astral-sh/uv) and Docker.

```bash
git clone https://github.com/Quorlo/quorlo.git
cd quorlo
uv sync
docker compose up -d        # Postgres with the demo schema on localhost:15432

export QUORLO_DSN=postgresql://quorlo:quorlo@localhost:15432/quorlo_demo
uv run quorlo scan
```

```
                 AI readiness: quorlo_demo.retail_raw (postgres)

 Table                  Score   Meaning   Certified   Trust   Governed   Findings
 ────────────────────────────────────────────────────────────────────────────────
 daily_revenue_v2         25%       20%          0%      0%       100%          9
 stg_imp_01               25%        0%        100%      0%       100%         11
 cust_mstr                28%       24%        100%      0%         0%         23
 ord_ln                   30%        8%        100%      0%       100%         11
 revenue_daily            38%       40%          0%      0%       100%          5
 v_ord_summary (view)     40%       10%        100%     n/a       100%          9
 ord_hdr                  68%       68%        100%      0%       100%          9
 dim_product             100%      100%        100%    100%       100%          0

Overall: 44% across 8 tables, 77 findings
  What is it?               34%
  Is it the right one?      75%
  Can I trust it?           14%
  Am I allowed to use it?   88%
  Not scored yet (no checks): lineage
Scanned 2 schemas, 8 tables, 39 columns in 0.03s
  fetch 0.02s (7 queries) · checks 0.00s · scoring 0.00s · persistence 0.00s
Saved as run 20261003T174608Z-b2a84e.
Next: quorlo findings                     what to fix, worst table first
      quorlo findings --table stg_imp_01  start with the lowest-scoring table
```

Each problem shows up under the question it gets in the way of. `stg_imp_01` has columns named `c1`, `c2`, `f1` and `f2` and no documentation, so it scores 0% on *Meaning*. `cust_mstr` holds names, emails and phone numbers nobody marked as personal data, so it fails *Governed*. `revenue_daily` and `daily_revenue_v2` look like the same data and neither says which to use, so both fail *Certified*. Almost nothing records when it was last loaded, so *Trust* is low everywhere. `dim_product` gets everything right and scores 100%.

Every scan is saved, so the next one tells you what changed since the last, and `quorlo diff` lists exactly which findings were resolved and which are new.

More options:

```bash
uv run quorlo findings                    # what to fix, worst table first, with fixes
uv run quorlo findings --table cust_mstr  # one table; also --dimension, --check
uv run quorlo scan --schema retail_raw    # scan one schema (repeat for more)
uv run quorlo scan --format json          # machine-readable report
uv run quorlo diff                        # compare the last two runs
uv run quorlo runs                        # list saved runs
uv run quorlo connectors                  # installed connectors and what they may do
```

The scan reads only Postgres system catalogs, over a connection the driver marks read-only. It never selects from your tables. Row counts come from planner statistics.

Checks cover four of the five questions so far: descriptions, keys and readable names (*What is it?*), near-duplicate tables (*Is it the right one?*), freshness columns (*Can I trust it?*) and unmarked personal data (*Am I allowed to use it?*). Lineage comes later.

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
