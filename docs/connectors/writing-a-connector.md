# Writing a connector

A connector reads metadata from one platform and translates it into Quorlo's platform-neutral models. Connectors are plugins: a separate package can add one without changing Quorlo.

!!! tip "Talk to us first"
    Please open a [Discussion](https://github.com/Quorlo/quorlo/discussions) before starting a connector, so we can agree on scope.

## The contract

A connector is a class with the shape of the `quorlo.connector.Connector` protocol. It does **not** need to inherit from anything in Quorlo.

```python
from collections.abc import Iterator, Sequence
from typing import ClassVar, Self

from quorlo.connector import (
    ConnectionConfig,
    ConnectorCapabilities,
    ConnectorError,
    DatabaseInfo,
    FetchStats,
)
from quorlo.models import Schema


class MySQLConnector:
    name: ClassVar[str] = "mysql"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities()

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config  # don't connect yet; connect on first use

    def test_connection(self) -> None:
        """Raise ConnectorError if the platform can't be reached."""

    def describe(self) -> DatabaseInfo:
        """Name, platform and credential-free location. Must not fetch any tables."""

    def list_schemas(self) -> list[str]:
        """Names of all non-system schemas."""

    def iter_schemas(self, schemas: Sequence[str] | None = None) -> Iterator[Schema]:
        """Yield each schema, complete with its tables, one at a time."""

    @property
    def stats(self) -> FetchStats:
        """Queries issued, rows read and time spent fetching so far."""

    def close(self) -> None: ...

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
```

## Fetch in batches, stream by schema

Scans have to work on estates with tens of thousands of tables, so the contract has two rules:

1. **Batch-first.** Fetch each schema with a **fixed number of queries**, however many tables it has: one query for all its tables, one for all their columns, one for all their constraints. Never run a query per table. The Postgres connector uses exactly three per schema, plus one for the schema list.
2. **Stream.** `iter_schemas` is a generator that yields one complete `Schema` at a time. Quorlo checks it, saves it and drops it before asking for the next one, so memory stays bounded by your largest schema rather than the whole estate.

And one more, for correctness: read **one consistent snapshot**. All of a scan's queries should see the platform at the same moment, so a schema change during the scan can't show up half-applied. In Postgres that's one `REPEATABLE READ`, read-only transaction around the whole stream. Close it in a `finally` block: a scan can stop part-way.

Count every query in `stats`. Quorlo prints the count after each scan, and your tests should hold it constant. The Postgres connector has an integration test that scans a schema with 1 table and one with 60, and asserts both cost the same number of queries.

To collect everything at once, for example in a test, use `quorlo.connector.read_database(connector)`.

### `ConnectionConfig`

What the user passed in:

| Field | Meaning |
| --- | --- |
| `dsn` | A `SecretStr`. Call `dsn.get_secret_value()` only where the driver needs it, and never include it in an error message. |
| `read_only` | Always `True` for scanning. Refuse to run if it is `False` and you can't honour it. |
| `allow_sample_values` | `False` unless the user explicitly opted in. |
| `options` | Free-form, connector-specific settings, such as a connect timeout. |

### `ConnectorCapabilities`

Declares what the connector may do. Everything beyond reading metadata defaults to `False`:

```python
ConnectorCapabilities(reads_data=False, metadata_write_back=False, sample_values=False)
```

`quorlo connectors` shows these to users, so keep them honest.

### Errors

Raise `quorlo.connector.ConnectorError` for failures the user can act on: can't connect, permission denied, unknown schema. Raise an unknown schema from `iter_schemas`, before yielding anything. The CLI prints the message and exits with code 2. Re-raise driver errors as `ConnectorError` with `from None`, so the traceback can't leak a DSN.

## Building the models

`iter_schemas()` yields `quorlo.models.Schema` objects. The models are frozen and reject unknown fields.

```python
from quorlo.models import Column, DataType, Schema, Table, TableKind, TableRef, TypeKind

Schema(
    name="sales",
    tables=(
        Table(
            name="orders",
            kind=TableKind.TABLE,
            description="One row per order.",
            columns=(
                Column(
                    name="order_id",
                    data_type=DataType(raw="int", kind=TypeKind.INTEGER),
                    ordinal=1,
                    nullable=False,
                ),
            ),
            primary_key=("order_id",),
            ref=TableRef(database="shop", schema="sales", table="orders"),
        ),
    ),
)
```

Keep turning rows into models separate from fetching them, in a class you can unit-test with plain dicts. The Postgres connector's `SchemaAssembler` is an example.

- Keep the platform's own type spelling in `DataType.raw`, and map it to the closest neutral `TypeKind`. Use `TypeKind.OTHER` when nothing fits.
- `row_count_estimate` must come from catalog statistics. Never count rows.
- There is deliberately no place for sample values or rows. Don't add one.

## Registering the connector

Register the class in the `quorlo.connectors` entry-point group in your package's `pyproject.toml`:

```toml
[project.entry-points."quorlo.connectors"]
mysql = "quorlo_mysql:MySQLConnector"
```

Once installed in the same environment, it shows up in `quorlo connectors` and works with `quorlo scan --connector mysql`. The built-in Postgres connector registers the same way.

## Rules for connectors

- Use read-only credentials, and enforce read-only in the driver or session where the platform allows it.
- Read schema, comments, tags and constraints. Read sample values or query history only when the user enables it.
- Write back only metadata (comments, tags, descriptions), never data.
- Ship unit tests that run without the platform, and integration tests marked `@pytest.mark.integration` against a local or containerized instance.

The [Postgres connector](https://github.com/Quorlo/quorlo/tree/main/src/quorlo/connectors/postgres) is a complete example, one module per job:
- `queries`: the catalog SQL;
- `runner`: one read-only snapshot transaction, with every query counted;
- `catalog`: turns rows into models;
- `types`: maps platform types to neutral ones;
- `connector`: puts the pieces together.
