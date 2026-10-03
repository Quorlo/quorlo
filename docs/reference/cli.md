# CLI

```
quorlo [COMMAND] [OPTIONS]
```

## `quorlo scan`

Scan a platform read-only and score how AI-ready each table is.

```bash
quorlo scan [--dsn DSN] [--connector NAME] [--schema NAME]... [--details] [--format table|json]
```

| Option | Default | Description |
| --- | --- | --- |
| `--dsn` | `$QUORLO_DSN` | Connection string. Prefer the environment variable, which keeps passwords out of shell history. Required one way or the other. |
| `--connector`, `-c` | `postgres` | Which installed connector to use. See `quorlo connectors`. |
| `--schema`, `-s` | all non-system schemas | Schema to scan. Repeat for several. An unknown schema is an error. |
| `--details` | off | After the summary, list every finding. |
| `--format`, `-f` | `table` | `table` for a terminal summary, `json` for a machine-readable report. |

**Exit codes:** `0` when the scan completed, `2` when it couldn't, for example an unknown connector, a connection failure or an unknown schema. The error is printed to stderr. Today a low score does not change the exit code.

### JSON output

`--format json` prints the full report: overall and per-dimension scores, and for every table its scores, the result of each check and every finding.

```bash
quorlo scan --format json | jq '.tables[] | {table, score}'
```

```json
{
  "table": "quorlo_demo.retail_raw.stg_imp_01",
  "score": 0.0
}
```

The top level has `database`, `platform`, `score`, `dimensions`, `tables` and `findings_count`. Scores are fractions between 0 and 1, or `null` when nothing was evaluated.

## `quorlo connectors`

List installed connectors, the package that provides each, and what each one is allowed to do: read data, write metadata back, read sample values. A connector that fails to load is listed with its error rather than breaking the command.

## `quorlo version`

Print the installed Quorlo version.
