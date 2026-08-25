"""Tests for bfv_api.standings."""

from __future__ import annotations

from bfv_api.standings import Match, show_standings


def test_show_standings() -> None:
    inputs = [
        Match("A", "B", 1, 1, 1, 1),
        Match("B", "C", 1, 1, 1, 1),
        Match("C", "A", 1, 0, 1, 1),
        Match("A", "D", 2, 1, 1, 1),
        Match("D", "B", 1, 1, 1, 1),
        Match("C", "D", 0, 1, 1, 1),
    ]

    show_standings(inputs)
