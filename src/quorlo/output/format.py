"""Small formatting helpers shared by every view."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text

from quorlo.history import ScoreChange


def score_text(score: float | None) -> Text:
    if score is None:
        return Text("n/a", style="dim")
    style = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "red"
    return Text(f"{score:.0%}", style=style)


def pct(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.0%}"


def points(score: float) -> int:
    """The whole percentage shown for a score, rounded exactly as `pct` rounds it."""
    return int(f"{score * 100:.0f}")


def delta_text(change: ScoreChange) -> Text:
    text = Text(f"{pct(change.before)} → ").append_text(score_text(change.after))
    if change.before is not None and change.after is not None:
        # The difference of the two numbers on screen, so "44% → 48%" never reads "+3".
        moved = points(change.after) - points(change.before)
        if moved:
            unit = "pt" if abs(moved) == 1 else "pts"
            text.append(f" ({moved:+d} {unit})", style="green" if moved > 0 else "red")
    return text


def count(n: int, noun: str, plural: str | None = None) -> str:
    return f"{n:,} {noun if n == 1 else plural or noun + 's'}"


def ago(then: datetime, now: datetime) -> str:
    seconds = max(0, int((now - then).total_seconds()))
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"
