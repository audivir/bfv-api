"""Tests for bfv_api.standings."""

from __future__ import annotations

import pytest

from bfv_api.standings import Match, Team, Tiebreaker, show_standings, sort_group


def test_sort_group_head_to_head_requires_special() -> None:
    teams = [Team("A"), Team("B")]
    with pytest.raises(ValueError, match="No tiebreaker given"):
        sort_group(teams, Tiebreaker.HEAD_TO_HEAD, special=None)


def test_sort_group_head_to_head_no_matches_between_teams() -> None:
    team_a = Team("A")
    team_a.matches.append(Match("A", "X", 1, 0, 0, 0))
    team_b = Team("B")
    team_b.matches.append(Match("B", "Y", 1, 0, 0, 0))

    groups = sort_group([team_a, team_b], Tiebreaker.HEAD_TO_HEAD, special=[Tiebreaker.POINTS])
    assert groups == []


def test_sort_group_random() -> None:
    teams = [Team("A"), Team("B")]
    groups = sort_group(teams, Tiebreaker.RANDOM)
    assert {team.name for group in groups for team in group} == {"A", "B"}


def test_show_standings_unresolved_tie_raises() -> None:
    matches = [
        Match("A", "C", 1, 0, 0, 0),
        Match("B", "D", 1, 0, 0, 0),
    ]
    with pytest.raises(ValueError, match="Table contains non-team objects"):
        show_standings(matches, tiebreakers=[Tiebreaker.POINTS])


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
