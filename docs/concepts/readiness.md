# Readiness model

Quorlo measures how ready a table is for an AI agent, as scores between 0% and 100%: one overall and one for each of the five questions.

## Dimensions

Every check answers exactly one of the five questions. In the code these are the members of `quorlo.readiness.Dimension`:

| Dimension | Question | Shown as | Checks |
| --- | --- | --- | --- |
| `meaning` | What is it? | Meaning | descriptions, primary key, readable names |
| `certification` | Is it the right one? | Certified | near-duplicate tables |
| `trust` | Can I trust it? | Trust | freshness column |
| `lineage` | Where did it come from? | Lineage | planned: needs dbt or OpenLineage input |
| `governance` | Am I allowed to use it? | Governed | unmarked personal data |

A dimension with no checks is reported as *not scored yet*, never as 0% or 100%. Scores are always shown per dimension, because one opaque number can't tell a data owner what kind of gap they have.

## Checks and findings

A check reports only what is wrong, as **findings**. There are two kinds:

- a **table check** judges one table on its own. All but one of the built-in checks are this kind;
- an **estate check** judges tables against the rest of the estate, which is how near-duplicates are found. It observes each table as schemas stream past, keeping only a small signature, and reports once every table has been seen.

Each check declares:

- a **scope**: `table` (one verdict for the whole table) or `column` (one per column). The personal-data check is table-scoped on purpose: one unmarked column is enough to make a table unsafe to use, though its findings still name each column;
- a **severity**: `low`, `medium` or `high`;
- a **weight**: how much it counts towards the score;
- which tables it **applies to**. For example, views are not expected to have a primary key.

All built-in checks are listed in the [checks reference](../reference/checks.md).

## Scoring

Checks never compute scores; the engine does, in three steps.

**1. Each check gets a pass rate.** A table-scope check evaluates one unit per table, a column-scope check one per column:

```
pass rate = 1 - findings / units evaluated
```

**2. Each table gets a weighted average of its checks' pass rates**: per dimension using only that dimension's checks, and overall using all of them.

**3. A scan's scores are the average of its tables' scores.**

### Example

The *Meaning* score of a table with 20 columns, all documented and readably named, with a primary key but no table description:

| Check | Weight | Pass rate |
| --- | --- | --- |
| `table.description.missing` | 2 | 0 / 1 passed → 0% |
| `column.description.missing` | 1 | 20 / 20 → 100% |
| `table.primary_key.missing` | 1 | 1 / 1 → 100% |
| `column.name.cryptic` | 1 | 20 / 20 → 100% |

Meaning = (2 × 0 + 1 × 1 + 1 × 1 + 1 × 1) / 5 = **60%**.

Averaging per check, rather than counting every column as a unit, keeps a wide table's column checks from drowning out its table-level checks. Counted per unit, this table would score about 95% despite having no description at all.

!!! note "Nothing evaluated is not zero"
    If no check applies to a table (say, a view with no columns), its score is *n/a*, not 0%.
