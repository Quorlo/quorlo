"""A scan from start to finish: fetch, check, score and save, timing each phase.

Metadata streams through one schema at a time. Nothing holds the whole estate: the
connector yields a schema, the engine checks it, the store writes its snapshot and its
findings, and the schema is dropped before the next one is fetched.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from quorlo.connectors import Connector
from quorlo.history import RunHeader, RunStore, RunTarget, SinceLastRun
from quorlo.models import Schema
from quorlo.readiness import Finding, FindingList, FindingSink, ReadinessEngine, ScanReport
from quorlo.stats import Phase, PhaseClock, ScanStats


class ScanOutcome(BaseModel):
    """What a scan produced. Findings are in the store when the run was saved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    header: RunHeader
    report: ScanReport
    stats: ScanStats
    saved: bool
    since_last_run: SinceLastRun | None = None
    unsaved_findings: tuple[Finding, ...] = ()


class _Sizes:
    """Counts what streamed past, without keeping any of it."""

    def __init__(self) -> None:
        self.schemas = self.tables = self.columns = 0

    def count(self, schema: Schema) -> None:
        self.schemas += 1
        self.tables += len(schema.tables)
        self.columns += sum(len(t.columns) for t in schema.tables)


class _TimedSink:
    """Hands findings to the store, counting the time as persistence, not checks."""

    def __init__(self, sink: FindingSink, clock: PhaseClock) -> None:
        self._sink = sink
        self._clock = clock

    def add(self, findings: Iterable[Finding]) -> None:
        with self._clock.phase(Phase.PERSISTENCE):
            self._sink.add(findings)


class Scanner:
    """Runs scans with one engine, saving them to `store` when one is given."""

    def __init__(self, engine: ReadinessEngine, store: RunStore | None = None) -> None:
        self._engine = engine
        self._store = store

    def scan(self, connector: Connector, schemas: Sequence[str] | None = None) -> ScanOutcome:
        started = time.perf_counter()
        clock = PhaseClock()
        sizes = _Sizes()

        with clock.phase(Phase.FETCH):
            info = connector.describe()
        header = RunHeader.start(RunTarget.of(info), schemas)
        writer = self._store.open_run(header) if self._store else None
        memory = FindingList()
        assessment = self._engine.start(_TimedSink(writer, clock) if writer else memory)

        for schema in clock.timed(Phase.FETCH, connector.iter_schemas(schemas)):
            sizes.count(schema)
            with clock.phase(Phase.CHECKS):
                assessment.add(schema)
            if writer:
                with clock.phase(Phase.PERSISTENCE):
                    writer.add_schema(schema)

        with clock.phase(Phase.CHECKS):
            assessment.finish_checks()
        with clock.phase(Phase.SCORING):
            report = assessment.report(info.name, info.platform)

        # One measurement, both saved with the run and shown, so they always agree. Only
        # the final write below falls outside it.
        stats = self._stats(started, clock, connector, sizes)
        since = None
        if writer:
            writer.finish(report, datetime.now(UTC), stats)
            since = self._since_last_run(header, report)
        return ScanOutcome(
            header=header,
            report=report,
            stats=stats,
            saved=writer is not None,
            since_last_run=since,
            unsaved_findings=() if writer else tuple(memory),
        )

    def findings(self, outcome: ScanOutcome) -> Iterator[Finding]:
        """A scan's findings: streamed back from the store if saved, else from memory."""
        if outcome.saved:
            assert self._store is not None
            yield from self._store.findings(outcome.header.id)
        else:
            yield from outcome.unsaved_findings

    def _since_last_run(self, header: RunHeader, report: ScanReport) -> SinceLastRun | None:
        assert self._store is not None
        previous = self._store.previous(header)
        if previous is None:
            return None
        return SinceLastRun.between(self._store, previous, header.id, report)

    @staticmethod
    def _stats(started: float, clock: PhaseClock, connector: Connector, sizes: _Sizes) -> ScanStats:
        fetched = connector.stats
        return ScanStats(
            seconds=time.perf_counter() - started,
            phases=clock.totals(),
            queries=fetched.queries,
            rows=fetched.rows,
            schemas=sizes.schemas,
            tables=sizes.tables,
            columns=sizes.columns,
        )
