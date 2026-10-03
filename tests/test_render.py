from datetime import UTC, datetime, timedelta

import pytest

from quorlo.history import ScoreChange
from quorlo.render import _ago, _delta_text


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
    assert _delta_text(ScoreChange(before=before, after=after)).plain == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(5, "just now"), (60, "1 minute ago"), (7200, "2 hours ago"), (86400 * 3, "3 days ago")],
)
def test_ago(seconds, expected):
    now = datetime(2026, 10, 3, tzinfo=UTC)
    assert _ago(now - timedelta(seconds=seconds), now) == expected
