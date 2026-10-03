# Run history

Every `quorlo scan` is saved, so you can see whether your data is getting more AI-ready over time, and exactly what changed.

## Scan, fix, scan again

```bash
quorlo scan
```

```
...
Overall: 44% across 8 tables, 77 findings
Saved as run 20261003T174608Z-b2a84e.
```

Someone documents `ord_ln`, marks `cust_mstr.eml` as PII, and adds a new `notes` column without a description. The next scan of the same database says what moved:

```
Since last run (2 days ago): 44% → 48% (+4 pts), 3 resolved, 1 new
Saved as run 20261005T091200Z-baf7f9.
```

`quorlo diff` shows the detail:

```
Overall: 44% → 48% (+4 pts)
  What is it?               34% → 39% (+5 pts)
  Is it the right one?      75% → 75%
  Can I trust it?           14% → 14%
  Am I allowed to use it?   88% → 88%
Findings: 3 resolved, 1 new, 74 unchanged

 Table                  Score                 Resolved   New
 ───────────────────────────────────────────────────────────
 retail_raw.cust_mstr   28% → 29% (+1 pt)            2     0
 retail_raw.ord_ln      30% → 56% (+26 pts)          1     1

New findings
  retail_raw.ord_ln.notes: Column has no description. (column.description.missing)

Resolved findings
  retail_raw.cust_mstr.eml: Column has no description. (column.description.missing)
  retail_raw.cust_mstr.eml: Column looks like personal data (email address) but is not
marked as PII. (column.pii.unclassified)
  retail_raw.ord_ln: Table has no description. (table.description.missing)
```

List saved runs with `quorlo runs`, and reprint one with `quorlo runs show RUN`. All commands are in the [CLI reference](../reference/cli.md#quorlo-runs).

## What gets compared with what

A run is only compared with earlier runs of the **same target**: the same platform, server and database. A scan limited with `--schema` is compared with earlier scans of the same schemas, so a partial scan never looks like a sudden drop.

Findings are matched by a **fingerprint** built from the check, the table, the column and, where needed, a detail such as the other table of a suspected duplicate. The wording of a message doesn't count, so improving a message in a new Quorlo release doesn't make old findings look new.

!!! note "When Quorlo itself changes"
    Every check has a version, and each run records which checks ran at which version. When the rules of a check change between two runs, or checks were added or removed, `quorlo diff` says so. A score that dropped because Quorlo got stricter shouldn't be mistaken for data getting worse.

## Where runs are stored

In a SQLite file in your user data directory:

| Platform | Path |
| --- | --- |
| Linux | `~/.local/share/quorlo/quorlo.db` (or `$XDG_DATA_HOME/quorlo/quorlo.db`) |
| macOS | `~/Library/Application Support/quorlo/quorlo.db` |
| Windows | `%LOCALAPPDATA%\quorlo\quorlo.db` |

Use another file with `--store PATH` or the `QUORLO_STORE` environment variable, for example a per-project history, or a file kept as a CI artifact. Skip saving a run with `--no-save`.

### What's in it

For each run: when it ran, the Quorlo version, the target, the scores, every finding, and a snapshot of the scanned metadata (table and column names, types, comments, keys). This is what makes future features like schema drift detection possible.

The store never holds data from your tables, and the target is recorded as `postgres://host:port/database`, built from the live connection, so it never contains a user name or password. It does hold your schema and its comments, so treat the file like any other copy of your schema documentation.

### Querying it directly

Besides the full run, scores and findings are stored as plain rows that any SQLite client can query:

```bash
sqlite3 ~/.local/share/quorlo/quorlo.db "
  SELECT r.started_at, s.score
  FROM table_scores s JOIN runs r ON r.id = s.run_id
  WHERE s.table_name = 'quorlo_demo.retail_raw.ord_ln' AND s.dimension = 'overall'
  ORDER BY r.started_at"
```

| Table | One row per |
| --- | --- |
| `runs` | run: id, timestamps, target, schemas, overall score, counts |
| `table_scores` | run, table and dimension (`overall`, `meaning`, `trust`, ...) |
| `findings` | finding in a run, with its fingerprint, check, severity, table and column |

The layout is versioned and upgraded automatically. A Quorlo that finds a store written by a newer version refuses to touch it rather than risk damaging it.
