"""Built-in readiness checks, one module per question they answer."""

from quorlo.readiness.base import Check
from quorlo.readiness.checks.certification import (
    DuplicateSuspected,
    column_type_overlap,
    declares_status,
)
from quorlo.readiness.checks.governance import PiiUnclassified, is_classified_as_pii
from quorlo.readiness.checks.meaning import (
    ColumnDescriptionMissing,
    ColumnNameCryptic,
    PrimaryKeyMissing,
    TableDescriptionMissing,
)
from quorlo.readiness.checks.trust import FreshnessUntracked

DEFAULT_CHECKS: tuple[Check, ...] = (
    TableDescriptionMissing(),
    ColumnDescriptionMissing(),
    PrimaryKeyMissing(),
    ColumnNameCryptic(),
    PiiUnclassified(),
    FreshnessUntracked(),
    DuplicateSuspected(),
)

__all__ = [
    "DEFAULT_CHECKS",
    "ColumnDescriptionMissing",
    "ColumnNameCryptic",
    "DuplicateSuspected",
    "FreshnessUntracked",
    "PiiUnclassified",
    "PrimaryKeyMissing",
    "TableDescriptionMissing",
    "column_type_overlap",
    "declares_status",
    "is_classified_as_pii",
]
