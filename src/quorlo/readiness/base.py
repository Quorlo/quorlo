"""Building blocks for readiness checks."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

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
    message: str
    remedy: str

    @property
    def target(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table


@runtime_checkable
class Check(Protocol):
    """A readiness check.

    A check only reports what is wrong. It never computes a score: the engine derives
    how many units were evaluated from `scope` (one per table, or one per column) and
    from `applies_to`.
    """

    id: ClassVar[str]
    dimension: ClassVar[Dimension]
    scope: ClassVar[Scope]
    severity: ClassVar[Severity]
    weight: ClassVar[float]
    description: ClassVar[str]

    def applies_to(self, table: Table) -> bool: ...

    def run(self, table: Table) -> Iterable[Finding]: ...
