"""Where a scan's time goes, and how much it read."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

_T = TypeVar("_T")


class Phase(StrEnum):
    FETCH = "fetch"
    CHECKS = "checks"
    SCORING = "scoring"
    PERSISTENCE = "persistence"


class PhaseClock:
    """Adds up time per phase, even when phases interleave or nest.

    A streaming scan alternates between phases for every schema, and some work happens
    inside another phase (findings are saved while checks run). Entering a phase pauses
    the one already running, so every moment is counted once, in the innermost phase.
    """

    def __init__(self, now: Callable[[], float] = time.perf_counter) -> None:
        self._now = now
        self._totals = dict.fromkeys(Phase, 0.0)
        self._running: list[Phase] = []
        self._since = 0.0

    @contextmanager
    def phase(self, phase: Phase) -> Iterator[None]:
        self._switch_to(phase)
        try:
            yield
        finally:
            self._leave()

    def timed(self, phase: Phase, items: Iterable[_T]) -> Iterator[_T]:
        """Iterate `items`, counting only the time spent producing each one as `phase`."""
        iterator = iter(items)
        while True:
            with self.phase(phase):
                try:
                    item = next(iterator)
                except StopIteration:
                    return
            yield item

    def totals(self) -> dict[Phase, float]:
        return dict(self._totals)

    def _switch_to(self, phase: Phase) -> None:
        now = self._now()
        if self._running:
            self._totals[self._running[-1]] += now - self._since
        self._running.append(phase)
        self._since = now

    def _leave(self) -> None:
        now = self._now()
        self._totals[self._running.pop()] += now - self._since
        self._since = now


class ScanStats(BaseModel):
    """The cost and size of one scan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seconds: float
    phases: dict[Phase, float]
    queries: int
    rows: int
    schemas: int
    tables: int
    columns: int
