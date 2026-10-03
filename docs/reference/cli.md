# CLI

```
quorlo [COMMAND] [OPTIONS]
```

## `quorlo scan`

Scan a platform read-only and score how AI-ready each table is.

```bash
quorlo scan [--dsn DSN] [--connector NAME] [--schema NAME]... [--details] [--format table|json]
            [--save | --no-save] [--store PATH]
```

| Option | Default | Description |
| --- | --- | --- |
| `--dsn` | `$QUORLO_DSN` | Connection string. Prefer the environment variable, which keeps passwords out of shell history. Required one way or the other. |
| `--connector`, `-c` | `postgres` | Which installed connector to use. See `quorlo connectors`. |
| `--schema`, `-s` | all non-system schemas | Schema to scan. Repeat for several. An unknown schema is an error. |
| `--details` | off | After the summary, list every finding. |
| `--format`, `-f` | `table` | `table` for a terminal summary, `json` for a machine-readable report. |
| `--save` / `--no-save` | save | Save the run to the [run history](../guides/run-history.md). |
| `--store` | `$QUORLO_STORE`, else the user data directory | The run history file. |

After the summary come how the run compares with the previous run of the same database and schemas (when there is one), where the time went, and the run id:

```
Since last run (2 days ago): 44% → 48% (+4 pts), 3 resolved, 1 new
Scanned 2 schemas, 8 tables, 39 columns in 0.42s
  fetch 0.12s (7 queries) · checks 0.20s · scoring 0.01s · persistence 0.09s
Saved as run 20261003T174608Z-baf7f9.
```

The timing line splits the scan into phases. *fetch* is reading metadata from the platform, with the number of queries it took. *checks* is running the checks. *scoring* is turning results into scores. *persistence* is writing the run history. Schemas stream through these phases one at a time, so the times are totals across all schemas.

**Exit codes:** `0` when the scan completed, `2` when it couldn't, for example an unknown connector, a connection failure, an unknown schema or an unusable `--store`. The error is printed to stderr. Today a low score does not change the exit code.

### JSON output

`--format json` prints the full report: overall and per-dimension scores, for every table its scores and the result of each check, every finding, and the scan's timing.

```bash
quorlo scan --format json | jq '.tables[] | {table, score}'
```

```json
{
  "table": "quorlo_demo.retail_raw.stg_imp_01",
  "score": 0.0
}
```

The top level has `database`, `platform`, `checks` (each check that ran, with its version), `score`, `dimensions`, `tables`, `findings` (each with its `fingerprint`), `findings_count`, `stats` (seconds per phase, queries, rows, schemas, tables, columns) and, when the run was saved, `run_id`. Scores are fractions between 0 and 1, or `null` when nothing was evaluated.

## `quorlo runs`

List saved runs, newest first: id, when, which schemas, score, table and finding counts. When all listed runs share one target, it's shown in the title; otherwise each row names its target.

| Option | Default | Description |
| --- | --- | --- |
| `--limit` | `20` | How many runs to list. |
| `--store` | `$QUORLO_STORE`, else the user data directory | The run history file. |

### `quorlo runs show RUN`

Print the report of a saved run, as `quorlo scan` printed it. `RUN` is a run id or any prefix that matches exactly one run, such as `20261003T1746`. Takes `--details`, `--format` and `--store`.

## `quorlo diff`

Compare two saved runs: scores overall and per question, tables added or removed, which tables changed, and which findings are new or resolved.

```bash
quorlo diff                  # the latest run against the run before it, for the same target
quorlo diff BASE             # BASE against the latest run of the same target
quorlo diff BASE HEAD        # two specific runs
```

Takes `--format table|json` and `--store`. The comparison warns when the two runs are not strictly comparable: different databases or schemas, or check rules that changed between Quorlo versions. See [run history](../guides/run-history.md) for how findings are matched.

Exits with `2` when a run can't be found, or when there aren't two runs to compare.

## `quorlo connectors`

List installed connectors, the package that provides each, and what each one is allowed to do: read data, write metadata back, read sample values. A connector that fails to load is listed with its error rather than breaking the command.

## `quorlo version`

Print the installed Quorlo version.
