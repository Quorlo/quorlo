"""Catalog queries. Read only the system catalogs, never a user table."""

SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")

SCHEMAS_SQL = """
SELECT n.nspname AS name, obj_description(n.oid, 'pg_namespace') AS description
FROM pg_namespace n
WHERE n.nspname <> ALL(%(system)s::text[])
  AND n.nspname NOT LIKE 'pg\\_temp\\_%%'
  AND n.nspname NOT LIKE 'pg\\_toast\\_temp\\_%%'
ORDER BY n.nspname
"""

# Partitions are skipped; their partitioned parent (relkind 'p') represents them.
TABLES_SQL = """
SELECT n.nspname AS schema, c.relname AS name, c.relkind AS relkind,
       obj_description(c.oid, 'pg_class') AS description,
       c.reltuples::bigint AS reltuples
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND NOT c.relispartition
  AND n.nspname = %(schema)s
ORDER BY n.nspname, c.relname
"""

COLUMNS_SQL = """
SELECT n.nspname AS schema, c.relname AS table, a.attnum AS ordinal, a.attname AS name,
       format_type(a.atttypid, a.atttypmod) AS type, t.typtype AS typtype,
       NOT a.attnotnull AS nullable,
       col_description(c.oid, a.attnum) AS description,
       pg_get_expr(d.adbin, d.adrelid) AS default
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t ON t.oid = a.atttypid
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attnum > 0 AND NOT a.attisdropped
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND NOT c.relispartition
  AND n.nspname = %(schema)s
ORDER BY n.nspname, c.relname, a.attnum
"""

CONSTRAINTS_SQL = """
SELECT con.conname AS name, con.contype AS type, n.nspname AS schema, c.relname AS table,
       ARRAY(SELECT a.attname::text FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
             ORDER BY k.ord) AS columns,
       fn.nspname AS ref_schema, fc.relname AS ref_table,
       ARRAY(SELECT a.attname::text FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum
             ORDER BY k.ord) AS ref_columns
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE con.contype IN ('p', 'u', 'f')
  AND n.nspname = %(schema)s
ORDER BY n.nspname, c.relname, con.conname
"""
