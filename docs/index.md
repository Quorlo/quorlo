# Quorlo

**Make your data AI-ready.** Quorlo scans your data platforms, scores how ready each table is for AI agents, drafts the missing metadata, and writes what your data owners approve back to the catalogs you already use.

!!! warning "Pre-alpha"
    The first slice works: a read-only Postgres scan that scores four of the five questions; lineage comes later. Enrichment, review and write-back are still being designed, and nothing is on PyPI yet. Feedback is welcome in [Discussions](https://github.com/Quorlo/quorlo/discussions).

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

Quorlo scores every table against these questions, and tells you where the biggest gaps are. See [the readiness model](concepts/readiness.md).

## How it works

1. **Scan.** Connect read-only to your platforms and score readiness per table and column.
2. **Enrich.** Draft descriptions, code meanings, keys and PII tags. *(planned)*
3. **Review.** High-confidence results can be auto-accepted; uncertain ones go to the data owner. *(planned)*
4. **Write back.** Approved metadata lands in Unity Catalog, Snowflake, dbt YAML and more. *(planned)*

Quorlo is not a catalog. It never becomes another system of record.

## Try it

The [getting started guide](getting-started.md) scans a deliberately messy demo database in a couple of minutes.
