import pytest

from quorlo.stats import Phase, PhaseClock


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    time = FakeTime()
    return PhaseClock(now=time), time


def test_phases_accumulate_across_interleaving(clock):
    clock, time = clock
    for _ in range(3):
        with clock.phase(Phase.FETCH):
            time.advance(1)
        with clock.phase(Phase.CHECKS):
            time.advance(2)
    totals = clock.totals()
    assert (totals[Phase.FETCH], totals[Phase.CHECKS]) == (3, 6)
    assert totals[Phase.SCORING] == 0


def test_nested_phase_pauses_the_outer_one(clock):
    clock, time = clock
    with clock.phase(Phase.CHECKS):
        time.advance(1)
        with clock.phase(Phase.PERSISTENCE):
            time.advance(5)
        time.advance(1)
    totals = clock.totals()
    assert (totals[Phase.CHECKS], totals[Phase.PERSISTENCE]) == (2, 5)
    assert sum(totals.values()) == 7  # every moment counted once


def test_timed_counts_only_producing_items(clock):
    clock, time = clock

    def slow_items():
        for item in "ab":
            time.advance(10)
            yield item

    seen = []
    for item in clock.timed(Phase.FETCH, slow_items()):
        time.advance(1)  # the consumer's own work is not fetch time
        seen.append(item)
    assert seen == ["a", "b"]
    assert clock.totals()[Phase.FETCH] == 20


def test_phase_is_closed_when_the_body_raises(clock):
    clock, time = clock
    with pytest.raises(ValueError), clock.phase(Phase.FETCH):
        time.advance(4)
        raise ValueError
    with clock.phase(Phase.CHECKS):
        time.advance(1)
    assert clock.totals()[Phase.FETCH] == 4
    assert clock.totals()[Phase.CHECKS] == 1
