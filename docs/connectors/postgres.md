# Postgres

Built in. Scans tables, views, materialized views, foreign tables and partitioned tables.

| Capability | |
| --- | --- |
| Reads data | No |
| Writes metadata back | No (reports only) |
| Reads sample values | No |

## Connecting

Any [libpq connection string](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING) works, as a URI or as key-value pairs:

```bash
export QUORLO_DSN=postgresql://quorlo_reader@db.internal:5432/warehouse
quorlo scan
```

Standard libpq environment variables and files (`PGPASSWORD`, `.pgpass`, `PGSSLMODE`, ...) apply as usual.

### Permissions

Quorlo reads only the system catalogs (`pg_class`, `pg_attribute`, `pg_constraint`, ...), which every role can read by default. It does **not** need `SELECT` on your tables. A dedicated login role with no other grants is enough:

```sql
CREATE ROLE quorlo_reader LOGIN PASSWORD '...';
```

## What it reads

| Metadata | Source |
| --- | --- |
| Schemas and their comments | `pg_namespace` |
| Tables, views and their kind | `pg_class` |
| Columns, types, nullability, defaults | `pg_attribute`, `pg_attrdef`, `format_type()` |
| Table and column comments | `obj_description()`, `col_description()` |
| Primary keys, unique constraints, foreign keys | `pg_constraint` |
| Approximate row count | `pg_class.reltuples` (planner statistics) |

System schemas (`pg_catalog`, `information_schema`, `pg_toast`, temporary schemas) are skipped. Partitions are skipped in favour of their partitioned parent table.

Each schema costs exactly **three queries** (tables, columns, constraints), plus one for the schema list, however many tables it has. Schemas stream one at a time, so memory stays bounded by the largest schema. A scan prints its query count, for example `fetch 0.02s (7 queries)` for two schemas.

All of a scan's queries run in **one read-only `REPEATABLE READ` transaction**, so they see a single consistent snapshot. A table created or altered while the scan runs is not half-seen.

!!! note "Row counts"
    The row count is the planner's estimate from the last `ANALYZE` or autovacuum. It is empty for a table that has never been analyzed. Quorlo never counts rows.

## Read-only, enforced by the server

The connection is opened with psycopg's `read_only = True`, which makes every transaction `READ ONLY`. Postgres itself rejects any write, whatever query is sent. The connector refuses to start on a connection configured for writing.
