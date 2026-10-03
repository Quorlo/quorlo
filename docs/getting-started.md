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
                       AI readiness: quorlo_demo (postgres)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┓
┃ Table                                   ┃ Kind  ┃ Score ┃ Meaning ┃ Findings ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━┩
│ quorlo_demo.retail_raw.stg_imp_01       │ table │    0% │      0% │       10 │
│ quorlo_demo.retail_raw.ord_ln           │ table │    8% │      8% │       10 │
│ quorlo_demo.retail_raw.v_ord_summary    │ view  │   10% │     10% │        9 │
│ quorlo_demo.retail_raw.daily_revenue_v2 │ table │   20% │     20% │        7 │
│ quorlo_demo.retail_raw.cust_mstr        │ table │   24% │     24% │       17 │
│ quorlo_demo.retail_raw.revenue_daily    │ table │   40% │     40% │        3 │
│ quorlo_demo.retail_raw.ord_hdr          │ table │   68% │     68% │        8 │
│ quorlo_demo.retail_raw.dim_product      │ table │  100% │    100% │        0 │
└─────────────────────────────────────────┴───────┴───────┴─────────┴──────────┘
Overall: 34% across 8 tables, 64 findings
  What is it?               34%
  Not scored yet (no checks): certification, trust, lineage, governance
```

`stg_imp_01` has columns named `c1`, `c2`, `f1` and `f2` and no documentation, so it scores 0%. `dim_product` is fully described and keyed, so it scores 100%.

## See every finding

```bash
uv run quorlo scan --details
```

Each finding names the table or column, the check that raised it, its severity and the problem. All checks are listed in the [checks reference](reference/checks.md).

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
