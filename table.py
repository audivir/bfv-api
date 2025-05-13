"""Create a sports table from a list of matches."""

from typing import NamedTuple
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import deque
import uuid
from collections.abc import Iterable

POINTS_FOR_WIN = 3
POINTS_FOR_DRAW = 1


class Match(NamedTuple):
    home: str
    guest: str
    home_score: int
    guest_score: int
    home_fairplay: int
    guest_fairplay: int


@dataclass
class Team:
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


class OrderType(Enum):
    POINTS = auto()
    HEAD_TO_HEAD = auto()
    GOAL_DIFFERENCE = auto()
    GOALS_FOR = auto()
    WINS = auto()
    AWAY_GOALS_FOR = auto()
    RANDOM = auto()


def sort_group(
    teams: list[Team], type_: OrderType, special: list[OrderType] | None = None
) -> list[list[Team]]:
    """Sort teams by points."""
    if type_ is OrderType.HEAD_TO_HEAD:
        if not special:
            raise ValueError(
                "No tiebreaker given for head to head sort. Provide tiebreaker or disable head to head sort."
            )
        orig_teams = {team.name: team for team in teams}
        matches: list[Match] = []
        for team in teams:
            for match in team.matches:
                if match.home in orig_teams and match.guest in orig_teams:
                    matches.append(match)
        unique_matches = set(matches)
        if not unique_matches:
            print(
                f"No head to head matches found for {set(orig_teams)}. Continuing with whole table"
            )
        subtable = create_table(unique_matches)
        sorted_subtable = tiebreaker_sort(subtable.values(), deque(special))
        subgroups: list[list[Team]] = []
        for subgroup in sorted_subtable:
            if isinstance(subgroup, list):
                subgroups.append([orig_teams[team.name] for team in subgroup])
            else:
                subgroups.append([orig_teams[subgroup.name]])
        return subgroups

    def get_value(team: Team) -> int:
        if type_ is OrderType.POINTS:
            return team.points
        elif type_ is OrderType.GOAL_DIFFERENCE:
            return team.goals_for - team.goals_against
        elif type_ is OrderType.GOALS_FOR:
            return team.goals_for
        elif type_ is OrderType.WINS:
            return team.wins
        elif type_ is OrderType.AWAY_GOALS_FOR:
            return team.away_goals_for
        elif type_ is OrderType.RANDOM:
            return team.uuid
        else:
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
    teams: list[Team],
    tiebreakers: deque[OrderType],
    special_tiebreakers: list[OrderType] | None = None,
) -> list[Team | list[Team]]:
    if not tiebreakers:
        return [teams]

    current_type = tiebreakers.popleft()

    sorted_groups = sort_group(teams, current_type, special_tiebreakers)

    sorted_table: list[Team | list[Team]] = []
    # Group and resolve ties recursively
    for group in sorted_groups:
        if len(group) > 1:
            subsorted = tiebreaker_sort(group, tiebreakers.copy(), special_tiebreakers)
            sorted_table.extend(subsorted)
        else:
            sorted_table.extend(group)
    return sorted_table


def create_table(matches: Iterable[Match]) -> dict[str, Team]:
    """Create a sports table from a list of matches."""
    table: dict[str, Team] = {}
    for match in matches:
        home = table.setdefault(match.home, Team(match.home))
        guest = table.setdefault(match.guest, Team(match.guest))

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

    return table


def _show_table(table: Iterable[Team]) -> None:
    print("Rank\tTeam\t\t\t\t\tGames\tPoints\tWins\tDraws\tLosses\tGF\tGA\tFP\tUUID")
    for ix, team in enumerate(table):
        print(
            f"{ix + 1}\t{team.name:<32}\t{team.games}\t{team.points}\t{team.wins}\t{team.draws}\t{team.losses}\t{team.goals_for}\t{team.goals_against}\t{team.fairplay}\t{team.uuid}"
        )


def _verify_table(table: list[Team | list[Team]]) -> list[Team]:
    if not all(isinstance(team, Team) for team in table):
        raise ValueError("Table contains non-team objects")
    return table


def show_table(
    matches: list[Match],
    order: Iterable[OrderType] = OrderType,
    special: Iterable[OrderType] | None = (
        OrderType.POINTS,
        OrderType.GOAL_DIFFERENCE,
        OrderType.GOALS_FOR,
    ),
) -> None:
    table = create_table(matches)

    sorted_table = tiebreaker_sort(
        table.values(),
        deque(order),
        list(special) if special is not None else None,
    )
    sorted_table = _verify_table(sorted_table)
    _show_table(sorted_table)


def test_show_table() -> None:
    inputs = [
        Match("A", "B", 1, 1, 1, 1),
        Match("B", "C", 1, 1, 1, 1),
        Match("C", "A", 1, 0, 1, 1),
        Match("A", "D", 2, 1, 1, 1),
        Match("D", "B", 1, 1, 1, 1),
        Match("C", "D", 0, 1, 1, 1),
    ]

    show_table(inputs)
