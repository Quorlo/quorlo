# Checks

The built-in checks. Every one belongs to a [dimension](../concepts/readiness.md#dimensions), and all of them work from metadata only: names, types, comments, constraints and tags, never the data itself.

| ID | Dimension | Scope | Severity | Weight |
| --- | --- | --- | --- | --- |
| [`table.description.missing`](#tabledescriptionmissing) | meaning | table | high | 2 |
| [`column.description.missing`](#columndescriptionmissing) | meaning | column | medium | 1 |
| [`table.primary_key.missing`](#tableprimary_keymissing) | meaning | table | medium | 1 |
| [`column.name.cryptic`](#columnnamecryptic) | meaning | column | low | 1 |
| [`table.duplicate.suspected`](#tableduplicatesuspected) | certification | table | medium | 1 |
| [`table.freshness.untracked`](#tablefreshnessuntracked) | trust | table | medium | 1 |
| [`column.pii.unclassified`](#columnpiiunclassified) | governance | table | high | 1 |

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

## `table.duplicate.suspected`

Another scanned table looks like the same data, and neither says which one to use. An agent asked for "daily revenue" has two answers and no way to choose.

Two tables match when both are true:

- their names have the same words once version and copy markers are dropped and word order is ignored. The markers are `v`, `old`, `new`, `bak`, `backup`, `copy`, `tmp`, `temp`, `final`, `latest` and `prev`, plus a number right after one of them. So `revenue_daily`, `daily_revenue_v2` and `revenue_daily_bak_2023` all match, while `orders_2023` and `orders_2024`, or `table_1` and `table_2`, stay different tables;
- at least half of their column types are shared.

Tables are compared across schemas too, so `raw.orders` and `analytics.orders` can match. Each table with matches gets one finding that names up to five of them ("and 3 more"), however many there are.

The pair counts as resolved, with no findings, when either table declares its status: a `certified` or `deprecated` tag, or a description that says *certified*, *source of truth*, *deprecated*, *superseded* or *do not use*.

**Fix:** mark the table to use as certified (for example `COMMENT ON TABLE ... IS 'Source of truth for daily revenue.'`), mark the other as deprecated, or remove it.

## `table.freshness.untracked`

The table has no column that says when its rows were last loaded or changed, so an agent can't tell whether the data is current.

A table passes when it has a timestamp or date column whose name contains one of: `updated`, `modified`, `changed`, `loaded`, `load`, `ingested`, `ingestion`, `refreshed`, `synced`, `extracted`, `etl`. So `updated_at`, `last_modified`, `_etl_loaded_at` and `ingestion_ts` all count. `created_at` does not: it says when a row first appeared, not whether the table is up to date.

Applies to tables and materialized views. Views are skipped, since they are only as fresh as the tables they read.

The check looks for the column only. It never reads `max(updated_at)`, so it can't tell you how stale a table actually is.

**Fix:** add a timestamp such as `updated_at` or `loaded_at` that the load process maintains, and describe it.

## `column.pii.unclassified`

A column looks like personal data, judging only by its name and type, but nothing marks it as such. Agents and access policies can't treat it carefully if nobody said what it is.

Some words mean personal data wherever they appear:

| Kind | Words |
| --- | --- |
| Email address | `email`, `eml` |
| Phone number | `phone`, `phn`, `mobile` |
| Person name | `surname`, `firstname`, `lastname`, `fullname`, or `name` after `first`, `last`, `middle`, `given`, `family`, `full` or `maiden` |
| National identifier | `ssn`, `passport` |
| Date of birth | `dob`, `birthdate`, `birthday`, and `birth` (reported as "birth details") |
| Payment card number | `card` or `cc` followed by `number`, `no` or `num` |
| Bank account | `iban` |
| Salary | `salary` |
| Sensitive attribute | `gender`, `ethnicity`, `religion` |
| IP address | `ip`, or any column of type `inet` or `cidr` |

Other words only mean personal data in a table or column about people (named with words like `customer`, `cust`, `user`, `person`, `employee`, `patient`, `member` or `contact`): `name`, `nm`, `address`, `addr`, `street`, `postal`, `postcode`, `zip`, `zipcode`, `pc`. So `cust_mstr.nm` is flagged and `dim_product.product_name` is not.

A column counts as marked when it has a tag such as `pii`, `personal`, `personal_data`, `sensitive` or `gdpr` (or one starting with `pii`), or when its description mentions *PII*, *personal data*, *personally identifiable*, *personal information* or *sensitive*. Postgres has no column tags, so there the description is what counts.

Scored per table: one unmarked column fails the table, because an agent can't safely use any of it. Each column still gets its own finding.

**Fix:** tag the column as PII, or say so in its description, for example `COMMENT ON COLUMN customers.email IS 'Customer email address. PII.'`.
