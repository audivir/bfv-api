"""Generate sports table from list of matches."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable
logger = logging.getLogger(__name__)
POINTS_FOR_WIN = 3
POINTS_FOR_DRAW = 1


class Match(NamedTuple):
    """Container for match results and fair play statistics."""

    home: str
    guest: str
    home_score: int
    guest_score: int
    home_fairplay: int
    guest_fairplay: int


@dataclass
class Team:
    """Encapsulates statistics and metadata for a sports table team."""

    name: str
    games: int = 0
    points: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    away_goals_for: int = 0
    goals_against: int = 0
    fairplay: int = 0
    matches: list[Match] = field(default_factory=list, repr=False)
    uuid: str = field(default_factory=lambda: uuid.uuid4().hex[:5], repr=False)


class Tiebreaker(Enum):
    """Defines tiebreaking criteria for ordering a sports table."""

    POINTS = auto()
    HEAD_TO_HEAD = auto()
    GOAL_DIFFERENCE = auto()
    GOALS_FOR = auto()
    WINS = auto()
    AWAY_GOALS_FOR = auto()
    RANDOM = auto()


def sort_group(  # noqa: C901
    teams: list[Team], type_: Tiebreaker, special: list[Tiebreaker] | None = None
) -> list[list[Team]]:
    """Sort teams using specified tiebreaking criteria."""
    if type_ is Tiebreaker.HEAD_TO_HEAD:
        if not special:
            raise ValueError(
                "No tiebreaker given for head to head sort."
                " Provide tiebreaker or disable head to head sort."
            )
        orig_teams = {team.name: team for team in teams}
        matches: list[Match] = [
            match
            for team in teams
            for match in team.matches
            if match.home in orig_teams and match.guest in orig_teams
        ]
        unique_matches = set(matches)
        if not unique_matches:
            logger.warning(
                "No head to head matches found for %s. Continuing with whole table", set(orig_teams)
            )
        sub_teams = create_standings(unique_matches)
        sub_standings = tiebreaker_sort(sub_teams, deque(special))
        sub_groups: list[list[Team]] = []
        for sub_group in sub_standings:
            if isinstance(sub_group, list):
                sub_groups.append([orig_teams[team.name] for team in sub_group])
            else:
                sub_groups.append([orig_teams[sub_group.name]])
        return sub_groups

    def get_value(team: Team) -> int:
        if type_ is Tiebreaker.POINTS:
            return team.points
        if type_ is Tiebreaker.GOAL_DIFFERENCE:
            return team.goals_for - team.goals_against
        if type_ is Tiebreaker.GOALS_FOR:
            return team.goals_for
        if type_ is Tiebreaker.WINS:
            return team.wins
        if type_ is Tiebreaker.AWAY_GOALS_FOR:
            return team.away_goals_for
        if type_ is Tiebreaker.RANDOM:
            return int(team.uuid, 16)
        raise ValueError(f"Invalid order type: {type_}")

    sorted_teams = sorted(teams, key=get_value, reverse=True)
    groups: list[list[Team]] = []
    for team in sorted_teams:
        if not groups or get_value(groups[-1][0]) != get_value(team):
            groups.append([team])
        else:
            groups[-1].append(team)
    return groups


def tiebreaker_sort(
    teams: list[Team], tiebreakers: deque[Tiebreaker], special: list[Tiebreaker] | None = None
) -> list[Team | list[Team]]:
    """Sort teams using specified tiebreaking criteria.

    Args:
        teams: Teams to sort.
        tiebreakers: Sequence of tiebreakers to apply.
        special: Optional tiebreakers for `Tiebreaker.HEAD_TO_HEAD` resolution.

    Returns:
        Sorted list of teams or nested groups for unresolved ties.
    """
    if not tiebreakers:
        return [teams]

    current_type = tiebreakers.popleft()

    sorted_groups = sort_group(teams, current_type, special)

    sorted_table: list[Team | list[Team]] = []
    # recursively resolve ties within groups.
    for group in sorted_groups:
        if len(group) > 1:
            subsorted = tiebreaker_sort(group, tiebreakers.copy(), special)
            sorted_table.extend(subsorted)
        else:
            sorted_table.extend(group)
    return sorted_table


def create_standings(matches: Iterable[Match]) -> list[Team]:
    """Generate league standings from a sequence of matches."""
    standings: dict[str, Team] = {}
    for match in matches:
        home = standings.setdefault(match.home, Team(match.home))
        guest = standings.setdefault(match.guest, Team(match.guest))

        home_score, guest_score = match.home_score, match.guest_score
        if home_score > guest_score:
            home.points += POINTS_FOR_WIN
            home.wins += 1
            guest.losses += 1
        elif home_score < guest_score:
            guest.points += POINTS_FOR_WIN
            guest.wins += 1
            home.losses += 1
        else:
            home.points += POINTS_FOR_DRAW
            guest.points += POINTS_FOR_DRAW
            home.draws += 1
            guest.draws += 1
        home.games += 1
        home.goals_for += home_score
        home.goals_against += guest_score
        home.fairplay += match.home_fairplay
        guest.games += 1
        guest.goals_for += guest_score
        guest.away_goals_for += guest_score
        guest.goals_against += home_score
        guest.fairplay += match.guest_fairplay
        home.matches.append(match)
        guest.matches.append(match)

    return list(standings.values())


def _show_standings(teams: Iterable[Team]) -> None:
    """Print league standings table to console."""
    print("Rank\tTeam\t\t\t\t\tGames\tPoints\tWins\tDraws\tLosses\tGF\tGA\tFP")  # noqa: T201
    for ix, team in enumerate(teams):
        print(  # noqa: T201
            f"{ix + 1}\t{team.name:<32}\t{team.games}\t{team.points}"
            f"\t{team.wins}\t{team.draws}\t{team.losses}"
            f"\t{team.goals_for}\t{team.goals_against}\t{team.fairplay}"
        )


def _verify_standings(teams: list[Team | list[Team]]) -> list[Team]:
    """Validate that standings list contains only Team objects."""
    if not all(isinstance(team, Team) for team in teams):
        raise ValueError("Table contains non-team objects")
    return teams  # type: ignore[return-value]


def show_standings(
    matches: list[Match],
    tiebreakers: Iterable[Tiebreaker] = Tiebreaker,
    special: Iterable[Tiebreaker] | None = (
        Tiebreaker.POINTS,
        Tiebreaker.GOAL_DIFFERENCE,
        Tiebreaker.GOALS_FOR,
    ),
) -> None:
    """Display league standings table.

    Args:
        matches: Sequence of matches to process.
        tiebreakers: Iterable of tiebreakers for ranking.
        special: Iterable of tiebreakers used specifically for `Tiebreaker.HEAD_TO_HEAD`.
    """
    teams = create_standings(matches)

    sorted_teams = tiebreaker_sort(
        teams, deque(tiebreakers), list(special) if special is not None else None
    )
    final_standings = _verify_standings(sorted_teams)
    _show_standings(final_standings)


def test_show_standings() -> None:
    """Verify that standings are correctly displayed for a set of match results."""
    inputs = [
        Match("A", "B", 1, 1, 1, 1),
        Match("B", "C", 1, 1, 1, 1),
        Match("C", "A", 1, 0, 1, 1),
        Match("A", "D", 2, 1, 1, 1),
        Match("D", "B", 1, 1, 1, 1),
        Match("C", "D", 0, 1, 1, 1),
    ]

    show_standings(inputs)
