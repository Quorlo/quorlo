# Writing a connector

A connector reads metadata from one platform and translates it into Quorlo's platform-neutral models. Connectors are plugins: a separate package can add one without changing Quorlo.

!!! tip "Talk to us first"
    Please open a [Discussion](https://github.com/Quorlo/quorlo/discussions) before starting a connector, so we can agree on scope.

## The contract

A connector is a class with the shape of the `quorlo.connector.Connector` protocol. It does **not** need to inherit from anything in Quorlo.

```python
from collections.abc import Sequence
from typing import ClassVar, Self

from quorlo.connector import ConnectionConfig, ConnectorCapabilities, ConnectorError
from quorlo.models import Database


class MySQLConnector:
    name: ClassVar[str] = "mysql"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities()

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config  # don't connect yet; connect on first use

    def test_connection(self) -> None:
        """Raise ConnectorError if the platform can't be reached."""

    def list_schemas(self) -> list[str]:
        """Names of all non-system schemas."""

    def scan(self, schemas: Sequence[str] | None = None) -> Database:
        """Read metadata for these schemas, or all non-system schemas when None."""

    def close(self) -> None: ...

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
```

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

Raise `quorlo.connector.ConnectorError` for failures the user can act on: can't connect, permission denied, unknown schema. The CLI prints the message and exits with code 2. Re-raise driver errors as `ConnectorError` with `from None`, so the traceback can't leak a DSN.

## Building the models

`scan()` returns a `quorlo.models.Database`. The models are frozen and reject unknown fields.

```python
from quorlo.models import Column, Database, DataType, Schema, Table, TableKind, TableRef, TypeKind

Database(
    name="shop",
    platform="mysql",
    schemas=(
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
        ),
    ),
)
```

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

The [Postgres connector](https://github.com/Quorlo/quorlo/blob/main/src/quorlo/connectors/postgres.py) is a complete example: catalog queries, a pure function that turns query rows into models, and a driver-enforced read-only connection.
