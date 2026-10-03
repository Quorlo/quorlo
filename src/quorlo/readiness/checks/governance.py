"""Checks for "Am I allowed to use it?": personal data that nobody marked."""

from __future__ import annotations

import re
from collections.abc import Iterable

from quorlo.models import Column, Table
from quorlo.readiness.base import Dimension, Finding, Scope, Severity
from quorlo.readiness.checks._base import BaseCheck
from quorlo.readiness.names import pii_category

PII_TAGS = frozenset({"pii", "personal", "personal_data", "sensitive", "gdpr"})
_PII_DESCRIPTION = re.compile(
    r"\b(pii|personal data|personally identifiable|personal information|sensitive)\b", re.I
)


def is_classified_as_pii(column: Column) -> bool:
    """Marked as personal data, by a platform tag or, where there are no tags, its description."""
    if any(tag.lower() in PII_TAGS or tag.lower().startswith("pii") for tag in column.tags):
        return True
    return bool(column.description and _PII_DESCRIPTION.search(column.description))


class PiiUnclassified(BaseCheck):
    id = "column.pii.unclassified"
    dimension = Dimension.GOVERNANCE
    # Scored per table: one unmarked personal-data column is enough to make the whole
    # table unsafe for an agent to use. Findings still name each column.
    scope = Scope.TABLE
    severity = Severity.HIGH
    weight = 1.0
    description = "Columns that look like personal data are marked as such."
    summary = "looks like personal data, not marked as PII"
    fix_hint = "tag it as PII, or end its description with 'PII.'"

    def run(self, table: Table) -> Iterable[Finding]:
        for col in table.columns:
            category = pii_category(col.name, table.name, col.data_type.raw)
            if category and not is_classified_as_pii(col):
                yield self.finding(
                    table.qualified_name,
                    f"Column looks like personal data ({category}) but is not marked as PII.",
                    "Tag the column as PII, or say so in its description, so agents and "
                    "access policies can treat it accordingly.",
                    column=col.name,
                )
