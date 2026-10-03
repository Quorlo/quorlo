from datetime import UTC, datetime, timedelta

import pytest

from quorlo.history import ScoreChange
from quorlo.output import stats_lines
from quorlo.output.format import ago, delta_text
from quorlo.stats import Phase, ScanStats


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (0.4447, 0.4766, "44% → 48% (+4 pts)"),  # raw delta is 3.2 pts; the screen shows 44 → 48
        (0.284, 0.29, "28% → 29% (+1 pt)"),
        (0.5, 0.4, "50% → 40% (-10 pts)"),
        (0.75, 0.7501, "75% → 75%"),
        (None, 0.5, "n/a → 50%"),
    ],
)
def test_delta_matches_the_numbers_shown(before, after, expected):
    assert delta_text(ScoreChange(before=before, after=after)).plain == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(5, "just now"), (60, "1 minute ago"), (7200, "2 hours ago"), (86400 * 3, "3 days ago")],
)
def test_ago(seconds, expected):
    now = datetime(2026, 10, 3, tzinfo=UTC)
    assert ago(now - timedelta(seconds=seconds), now) == expected


def test_stats_lines():
    stats = ScanStats(
        seconds=0.42,
        phases={Phase.FETCH: 0.12, Phase.CHECKS: 0.2, Phase.SCORING: 0.01, Phase.PERSISTENCE: 0.09},
        queries=1,
        rows=10,
        schemas=1,
        tables=8,
        columns=47,
    )
    size, phases = (line.plain for line in stats_lines(stats))
    assert size == "Scanned 1 schema, 8 tables, 47 columns in 0.42s"
    assert phases == "  fetch 0.12s (1 query) · checks 0.20s · scoring 0.01s · persistence 0.09s"
