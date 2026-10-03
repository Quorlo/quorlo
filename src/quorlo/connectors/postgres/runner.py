"""Runs catalog queries: one consistent, read-only snapshot, every query counted."""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import IsolationLevel
from psycopg.rows import dict_row

from quorlo.connector import ConnectionConfig, ConnectorError, FetchStats
from quorlo.connectors.postgres.catalog import Row


class QueryRunner:
    """Owns the connection to Postgres.

    Every transaction is READ ONLY, so the server rejects writes whatever is sent, and
    REPEATABLE READ, so all queries inside one `snapshot()` see the same moment in time.
    """

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._conn: psycopg.Connection | None = None
        self._stats = FetchStats()

    @property
    def stats(self) -> FetchStats:
        return self._stats

    @property
    def info(self) -> psycopg.ConnectionInfo:
        return self._connection().info

    @contextmanager
    def snapshot(self) -> Iterator[None]:
        """One transaction; ends with a rollback since there is never anything to commit."""
        conn = self._connection()
        try:
            yield
        finally:
            # A stream abandoned part-way can be closed after its connection already was.
            if not conn.closed:
                conn.rollback()

    def fetch(self, sql: str, params: Mapping[str, Any] | None = None) -> list[Row]:
        started = time.perf_counter()
        try:
            with self._connection().cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        except psycopg.Error as exc:
            raise ConnectorError(f"Postgres metadata query failed: {exc}") from None
        self._stats = self._stats.plus(rows=len(rows), seconds=time.perf_counter() - started)
        return rows

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _connection(self) -> psycopg.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _connect(self) -> psycopg.Connection:
        try:
            conn = psycopg.connect(
                self._config.dsn.get_secret_value(),
                row_factory=dict_row,
                connect_timeout=self._config.options.get("connect_timeout", 10),
                application_name="quorlo",
            )
        except psycopg.Error as exc:
            raise ConnectorError(f"Could not connect to Postgres: {exc}") from None
        conn.read_only = True
        conn.isolation_level = IsolationLevel.REPEATABLE_READ
        return conn
