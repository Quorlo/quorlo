# Getting started

Scan the bundled demo database: a retail schema with cryptic column names, undocumented status codes, a table without a primary key and near-duplicate tables.

## Requirements

- Python 3.11 or newer
- [uv](https://github.com/astral-sh/uv)
- Docker, for the demo database

## Run the demo

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

## Track progress

Every scan is saved. Fix something, scan again, and Quorlo tells you what changed:

```
Since last run (2 days ago): 44% → 48% (+4 pts), 3 resolved, 1 new
```

`quorlo diff` shows exactly which findings were resolved and which are new. See [run history](guides/run-history.md).

## See what to fix

```bash
uv run quorlo findings --table cust_mstr
```

```
Findings in run 20261003T192854Z-08798e · postgres://localhost:15432/quorlo_demo  (table: cust_mstr)

retail_raw.cust_mstr  (28%, 23 findings)
  What is it?
    table.description.missing   Table has no description.
                                fix: COMMENT ON TABLE retail_raw.cust_mstr IS '<what one row represents>';
    column.description.missing  nm, eml, phn, addr1, pc, cntry_cd, st, crt_dt · no column description
                                fix: COMMENT ON COLUMN retail_raw.cust_mstr.<column> IS '<meaning, units,
                                codes>';
    column.name.cryptic         nm, eml, phn, addr1, pc, cntry_cd, st, crt_dt · cryptic column name
                                fix: rename it, or explain the abbreviation in the column description
  Can I trust it?
    table.freshness.untracked   No column shows when rows were last loaded or updated.
                                fix: ALTER TABLE retail_raw.cust_mstr ADD COLUMN updated_at timestamp;  --
                                kept current by the load
  Am I allowed to use it?
    column.pii.unclassified     nm, eml, phn, addr1, pc · looks like personal data, not marked as PII
                                fix: tag it as PII, or end its description with 'PII.'
```

Without `--table`, every table is listed, worst first. Each check gets one line listing the columns it applies to, and a `fix:` line you can adapt. Narrow the list with `--dimension governance` or `--check column.pii.unclassified`, or add `--format json` for scripts. All checks are explained in the [checks reference](reference/checks.md).

## Scan your own database

Point `QUORLO_DSN` at any Postgres database. Quorlo only needs a role that can read the system catalogs, which every role can do by default; it never selects from your tables.

```bash
export QUORLO_DSN=postgresql://readonly_user@db.internal:5432/warehouse
uv run quorlo scan --schema sales --schema finance
```

!!! tip "Keep passwords out of shell history"
    Pass the DSN through `QUORLO_DSN` rather than `--dsn`, or use a [`.pgpass` file](https://www.postgresql.org/docs/current/libpq-pgpass.html) and leave the password out of the DSN entirely.

## Clean up

```bash
docker compose down -v      # stop the demo database and delete its data
```
