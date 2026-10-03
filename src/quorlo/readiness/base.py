"""Building blocks for readiness checks."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from quorlo.models import Database, Table


class Dimension(StrEnum):
    """The five questions an agent must be able to answer about a table."""

    MEANING = "meaning"
    CERTIFICATION = "certification"
    TRUST = "trust"
    LINEAGE = "lineage"
    GOVERNANCE = "governance"

    @property
    def question(self) -> str:
        return _QUESTIONS[self]


_QUESTIONS = {
    Dimension.MEANING: "What is it?",
    Dimension.CERTIFICATION: "Is it the right one?",
    Dimension.TRUST: "Can I trust it?",
    Dimension.LINEAGE: "Where did it come from?",
    Dimension.GOVERNANCE: "Am I allowed to use it?",
}


class Scope(StrEnum):
    """What one unit of a check is: the whole table, or each of its columns."""

    TABLE = "table"
    COLUMN = "column"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Finding(BaseModel):
    """One thing that is wrong with one table or column."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str
    dimension: Dimension
    severity: Severity
    scope: Scope
    table: str
    column: str | None = None
    key: str | None = Field(
        default=None,
        description="Tells apart findings a check raises more than once for the same target, "
        "e.g. the other table of a suspected duplicate.",
    )
    message: str
    remedy: str

    @property
    def target(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table

    @property
    def fingerprint(self) -> str:
        """Stable identity across runs: the same problem in the same place gets the same value.

        Built from what the finding is about, never from its wording, so rephrasing a
        message does not make an old finding look new.
        """
        parts = (self.check_id, self.table, self.column or "", self.key or "")
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]


_T = TypeVar("_T")


@dataclass(frozen=True)
class ScanContext:
    """Everything that was scanned, for checks that compare a table with the others."""

    tables: tuple[Table, ...]
    _by_name: dict[str, Table] = field(init=False, repr=False, compare=False)
    _memo: dict[Hashable, Any] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_name", {t.qualified_name: t for t in self.tables})
        object.__setattr__(self, "_memo", {})

    @classmethod
    def of(cls, database: Database) -> ScanContext:
        return cls(tuple(database.iter_tables()))

    @classmethod
    def of_tables(cls, tables: Sequence[Table]) -> ScanContext:
        return cls(tuple(tables))

    def table(self, qualified_name: str) -> Table | None:
        return self._by_name.get(qualified_name)

    def others(self, table: Table) -> Iterable[Table]:
        return (t for t in self.tables if t.qualified_name != table.qualified_name)

    def memo(self, key: Hashable, build: Callable[[], _T]) -> _T:
        """Build something derived from the scanned tables once per scan, e.g. an index.

        Cross-table checks run once per table; without this, each run would rebuild
        the same index and the check would cost O(n²).
        """
        if key not in self._memo:
            self._memo[key] = build()
        return self._memo[key]


@runtime_checkable
class Check(Protocol):
    """A readiness check.

    A check only reports what is wrong. It never computes a score: the engine derives
    how many units were evaluated from `scope` (one per table, or one per column) and
    from `applies_to`. `context` holds every scanned table, for checks that compare
    tables; most checks ignore it.

    Bump `version` whenever a change to the check's rules can change its findings, so
    run comparisons can tell a stricter check apart from data that got worse.
    """

    id: ClassVar[str]
    dimension: ClassVar[Dimension]
    scope: ClassVar[Scope]
    severity: ClassVar[Severity]
    weight: ClassVar[float]
    version: ClassVar[int]
    description: ClassVar[str]

    def applies_to(self, table: Table) -> bool: ...

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]: ...
