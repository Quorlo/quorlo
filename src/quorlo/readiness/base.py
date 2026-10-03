"""Building blocks for readiness checks."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from enum import StrEnum
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from quorlo.models import Table


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


class CheckInfo(Protocol):
    """What every check declares about itself.

    A check only reports what is wrong. It never computes a score: the engine derives how
    many units were evaluated from `scope` (one per table, or one per column) and from
    `applies_to`.

    Bump `version` whenever a change to the check's rules can change its findings, so run
    comparisons can tell a stricter check apart from data that got worse.
    """

    id: ClassVar[str]
    dimension: ClassVar[Dimension]
    scope: ClassVar[Scope]
    severity: ClassVar[Severity]
    weight: ClassVar[float]
    version: ClassVar[int]
    description: ClassVar[str]
    summary: ClassVar[str]
    """Short problem phrase for a line that groups many findings: "no table description"."""
    fix_hint: ClassVar[str]
    """One actionable line, with {table} and {column} placeholders."""

    def applies_to(self, table: Table) -> bool: ...


@runtime_checkable
class TableCheck(CheckInfo, Protocol):
    """Judges one table on its own. Most checks are this kind."""

    def run(self, table: Table) -> Iterable[Finding]: ...


@runtime_checkable
class EstateCheckRun(Protocol):
    """One scan's worth of state for an `EstateCheck`."""

    def observe(self, table: Table) -> None:
        """Called once per table the check applies to, as schemas stream past.

        Keep only what the final judgement needs, not the table itself, so memory grows
        with the number of tables rather than with their columns.
        """
        ...

    def findings(self) -> Iterable[Finding]:
        """Called once, after every table has been observed."""
        ...


@runtime_checkable
class EstateCheck(CheckInfo, Protocol):
    """Judges tables against the rest of the estate, e.g. to spot near-duplicates.

    The check object itself stays stateless; `start()` returns a fresh run per scan.
    """

    def start(self) -> EstateCheckRun: ...


Check = TableCheck | EstateCheck
