# Checks

The built-in checks. Every one belongs to a [dimension](../concepts/readiness.md#dimensions); today all of them answer *What is it?*.

| ID | Dimension | Scope | Severity | Weight |
| --- | --- | --- | --- | --- |
| [`table.description.missing`](#tabledescriptionmissing) | meaning | table | high | 2 |
| [`column.description.missing`](#columndescriptionmissing) | meaning | column | medium | 1 |
| [`table.primary_key.missing`](#tableprimary_keymissing) | meaning | table | medium | 1 |
| [`column.name.cryptic`](#columnnamecryptic) | meaning | column | low | 1 |

## `table.description.missing`

The table has no description, or only whitespace. An agent can't tell what one row represents.

**Fix:** describe what one row represents and what the table is used for. In Postgres: `COMMENT ON TABLE ... IS '...'`.

## `column.description.missing`

A column has no description. Reported once per undocumented column.

**Fix:** describe the column, including units and the meaning of any codes. In Postgres: `COMMENT ON COLUMN ... IS '...'`.

## `table.primary_key.missing`

The table declares no primary key, so an agent doesn't know what identifies a row, and can't safely join or deduplicate.

Applies to tables only. Views, materialized views and foreign tables can't declare a primary key, so they are not counted.

**Fix:** declare a primary key, or document which columns identify a row.

## `column.name.cryptic`

A column name an agent can't reliably interpret. A name is flagged when:

- it is a generic positional name, such as `c1`, `f2`, `col1` or `f_3`;
- it is two characters or shorter, such as `st` or `pc`;
- one of its words is a known legacy abbreviation: `amt`, `qty`, `dt`, `cd`, `nm`, `flg`, `st`, `addr`, `eml`, `cnt`, `typ`, `ind`;
- one of its words has no vowels, such as `cntry` or `phn`.

Names are split into words on underscores, camelCase and digits, so `cust_nm`, `custNm` and `addr1` are all checked word by word. Widely understood short words are never flagged: `id`, `url`, `uri`, `sku`, `ip`, `utc`, `iso`, `api`, `gps`, `vat`, `http`, `html`.

The check is about the name itself, so it flags a cryptic name even when the column is documented.

**Fix:** rename the column, or at least describe it so the abbreviation is explained.
