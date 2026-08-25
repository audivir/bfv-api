"""Verifies compliance with BFV Spielordnung Sec. 34 Nr. 2 (effective 06.07.2026).

Enforces rules regarding player eligibility across different teams within a club.

Implementation Details:
- Players appearing in a match of a higher team are ineligible for the next match of the lower
  team.
- Up to two players who appeared only in the second half of a match of a higher team are exempt.
- Kreisebene bonus: one additional arbitrary player is exempt if both teams play at Kreisebene.
- Kreisebene bonus: up to two additional second-half players are exempt if the higher team plays
  at Kreisebene and the lower team plays in B-/C-Klasse (or lowest tier A-Klasse).
- For clubs with 3+ teams, all higher teams are pooled when calculating restrictions.

Limitations:
- U23 exemption (Sec. 34 Nr. 2.2) is not implemented due to missing birthdate data in BFV API.
- A-Klasse lowest-tier status is tracked via KREISE_WHERE_A_KLASSE_IS_LOWEST.
- The 2.5 bonus quota accepts any second-half appearance, regardless of source level.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Annotated, NamedTuple, TypeAlias

import doctyper
from rich import print  # noqa: A004
from yaspin import yaspin

from bfv_api import BFV
from bfv_api.bfv import CompetitionLevel, StaffelInfo
from bfv_api.ineligibility import PlayersMatch, find_teams, get_matches_with_players

if TYPE_CHECKING:
    from datetime import date, datetime

# base quota for second-half-only exemptions (Sec. 34 Nr. 2.3)
SECOND_HALF_QUOTA = 2
# arbitrary exemption for Kreisebene-sourced players (Sec. 34 Nr. 2.4)
KREISEBENE_ARBITRARY_QUOTA = 1
# additional second-half-only exemptions for Kreisebene (Sec. 34 Nr. 2.5)
KREISEBENE_SECOND_HALF_BONUS = 2
# threshold minute for second-half-only player status
HALFTIME_MINUTE = 45

PlayerKey: TypeAlias = tuple[str, str]

# determine if A-Klasse is bottom tier for a Kreis (Sec. 34 Nr. 2.5) via substring match
# against `StaffelInfo.competitionArea`. defaults to False for unconfirmed Kreise.
KREISE_WHERE_A_KLASSE_IS_LOWEST: frozenset[str] = frozenset()


def is_a_klasse_lowest_tier(competition_area: str) -> bool:
    """Determines if A-Klasse is the bottom tier of the given Kreis (Sec. 34 Nr. 2.5)."""
    return any(name in competition_area for name in KREISE_WHERE_A_KLASSE_IS_LOWEST)


def is_kreisebene(level: CompetitionLevel) -> bool:
    """Determines if competition level is run at Kreis (district) level (Sec. 34 Nr. 2.4)."""
    return level <= CompetitionLevel.kreisliga  # type: ignore[operator,no-any-return]


def is_b_c_klasse(level: CompetitionLevel) -> bool:
    """Determines if level is B- or C-Klasse (Sec. 34 Nr. 2.5, unconditional part)."""
    return level <= CompetitionLevel.b_klasse  # type: ignore[operator,no-any-return]


def is_second_half_bonus_eligible(level: CompetitionLevel, competition_area: str) -> bool:
    """Determines if level is eligible for second half bonus (Sec. 34 Nr. 2.5)."""
    if is_b_c_klasse(level):
        return True
    return level == CompetitionLevel.a_klasse and is_a_klasse_lowest_tier(competition_area)


class AppearanceKind(Enum):
    """Defines participation type for player in higher team match."""

    FULL = auto()
    SECOND_HALF_ONLY = auto()


class HigherTeamAppearance(NamedTuple):
    """Stores player appearance in higher team match."""

    higher_team: int
    higher_team_level: CompetitionLevel
    kind: AppearanceKind
    kickoff: datetime
    home: str
    guest: str


class MatchViolation(NamedTuple):
    """Stores player usage in violation of Sec. 34 Nr. 2."""

    player_key: PlayerKey
    appearance: HigherTeamAppearance


class CheckedMatch(NamedTuple):
    """Stores results of violation check for lower-team match."""

    team: int
    date: date
    home: str
    guest: str
    exempt: list[PlayerKey]
    violations: list[MatchViolation]


def used_players(players: dict[PlayerKey, tuple[bool, int | None]]) -> set[PlayerKey]:
    """Returns the set of players who participated as starters or substitutes."""
    return {
        k
        for k, (substitute, substituted) in players.items()
        if not substitute or substituted is not None
    }


def classify_appearance(substitute: bool, substituted_minute: int | None) -> AppearanceKind:
    """Classifies higher-team appearance according to Sec. 34 Nr. 2.1/2.3."""
    if substitute and substituted_minute is not None and substituted_minute > HALFTIME_MINUTE:
        return AppearanceKind.SECOND_HALF_ONLY
    return AppearanceKind.FULL


def get_staffel_info(team_id: str) -> StaffelInfo:
    """Fetches current competition level and Kreis for team."""
    compound_id = BFV.get_team_matches(team_id).data.team.compoundId
    competition = BFV.get_competition(compound_id).data
    return StaffelInfo.from_model(competition)


def appearances_in_window(
    higher_matches: list[PlayersMatch],
    higher_team: int,
    higher_level: CompetitionLevel,
    window_start: datetime | None,
    window_end: datetime,
) -> dict[PlayerKey, HigherTeamAppearance]:
    """Collects appearances of higher team players within the specified time window."""
    appearances: dict[PlayerKey, HigherTeamAppearance] = {}
    for hm in higher_matches:
        if hm.kickoff >= window_end:
            break
        if window_start is not None and hm.kickoff <= window_start:
            continue
        for player_key in used_players(hm.players):
            substitute, substituted_minute = hm.players[player_key]
            kind = classify_appearance(substitute, substituted_minute)
            appearance = HigherTeamAppearance(
                higher_team, higher_level, kind, hm.kickoff, hm.homeTeam, hm.guestTeam
            )
            existing = appearances.get(player_key)
            if existing is None or (
                existing.kind is AppearanceKind.SECOND_HALF_ONLY and kind is AppearanceKind.FULL
            ):
                appearances[player_key] = appearance
    return appearances


def check_match(
    m: PlayersMatch,
    at_risk: dict[PlayerKey, HigherTeamAppearance],
    lower_level: CompetitionLevel,
    lower_competition_area: str,
) -> CheckedMatch:
    """Applies Sec. 34 Nr. 2.2-2.5 exemption quotas to the lower-team match."""
    used = used_players(m.players)
    relevant = {k: a for k, a in at_risk.items() if k in used}

    full_bans = {k: a for k, a in relevant.items() if a.kind is AppearanceKind.FULL}
    second_half = {k: a for k, a in relevant.items() if a.kind is AppearanceKind.SECOND_HALF_ONLY}

    exempt: list[PlayerKey] = []

    # apply Sec. 34 Nr. 2.4 quota for one arbitrary Kreisebene player.
    if is_kreisebene(lower_level):
        kreisebene_full = sorted(
            k for k, a in full_bans.items() if is_kreisebene(a.higher_team_level)
        )
        for key in kreisebene_full[:KREISEBENE_ARBITRARY_QUOTA]:
            exempt.append(key)
            del full_bans[key]

    # apply Sec. 34 Nr. 2.3 and 2.5 quotas for second-half-only appearances.
    quota = SECOND_HALF_QUOTA
    if is_second_half_bonus_eligible(lower_level, lower_competition_area):
        quota += KREISEBENE_SECOND_HALF_BONUS
    sorted_second_half = sorted(second_half)
    exempt.extend(sorted_second_half[:quota])
    violating_second_half = sorted_second_half[quota:]

    violations = [MatchViolation(k, full_bans[k]) for k in sorted(full_bans)]
    violations.extend(MatchViolation(k, second_half[k]) for k in violating_second_half)

    return CheckedMatch(m.team, m.kickoff.date(), m.homeTeam, m.guestTeam, exempt, violations)


def check_for_ineligibility(first_team_id: str, *team_ids: str) -> list[CheckedMatch]:
    """Checks lower-team matches for Sec. 34 Nr. 2 violations.

    Args:
        first_team_id: BFV team ID of highest-ranked team.
        team_ids: BFV team IDs of remaining club teams in descending rank order.
    """
    if not team_ids:
        return []

    all_team_ids = (first_team_id, *team_ids)
    staffel_infos = [get_staffel_info(tid) for tid in all_team_ids]
    levels = [info.competitionLevel for info in staffel_infos]

    with yaspin(text=f"Fetching matches for {len(all_team_ids)} teams...") as sp:
        matches_by_team = {
            ix: sorted(get_matches_with_players(tid, ix, sp.write), key=lambda pm: pm.kickoff)
            for ix, tid in enumerate(all_team_ids, start=1)
        }
        sp.ok("✓")

    checked: list[CheckedMatch] = []
    for team_ix in range(2, len(all_team_ids) + 1):
        own_matches = matches_by_team[team_ix]
        lower_level = levels[team_ix - 1]

        prev_kickoff: datetime | None = None
        for m in own_matches:
            at_risk: dict[PlayerKey, HigherTeamAppearance] = {}
            for higher_ix in range(1, team_ix):
                higher_appearances = appearances_in_window(
                    matches_by_team[higher_ix],
                    higher_ix,
                    levels[higher_ix - 1],
                    prev_kickoff,
                    m.kickoff,
                )
                for key, appearance in higher_appearances.items():
                    existing = at_risk.get(key)
                    if existing is None or (
                        existing.kind is AppearanceKind.SECOND_HALF_ONLY
                        and appearance.kind is AppearanceKind.FULL
                    ):
                        at_risk[key] = appearance

            lower_area = staffel_infos[team_ix - 1].competitionArea
            checked.append(check_match(m, at_risk, lower_level, lower_area))
            prev_kickoff = m.kickoff

    return checked


def main(club_id: str, pattern: Annotated[str | None, doctyper.Argument()] = None) -> None:
    """Checks for ineligible players according to Sec. 34 Nr. 2.

    Args:
        club_id: BFV club ID.
        pattern: Regex pattern to match team names.
    """
    club_name, found_teams = find_teams(club_id, pattern)

    print(f"[bold blue]=== {club_name} ===[/bold blue]")

    if not found_teams:
        extra = " different" if pattern else ""
        print(f"[bold red]No teams found, provide a{extra} pattern[/bold red]")
        raise SystemExit(1)

    for team_ix, t in enumerate(found_teams, start=1):
        print(f"[yellow]Found {t.name} (T{team_ix}) playing in {t.level.value}[/yellow]")

    if len(found_teams) == 1:
        print("[green bold]Only a single team provided. No violations possible![/green bold]")
        return

    checked = check_for_ineligibility(*(t.id for t in found_teams))

    for cm in checked:
        if not cm.violations:
            print(f"[green]No violations for {cm.home} - {cm.guest} ({cm.date})[/green]")
            continue

        print(f"[red bold]Violation(s) found for {cm.home} - {cm.guest} ({cm.date})[/]")
        for player_key, appearance in cm.violations:
            name, _ = player_key
            kind = "full" if appearance.kind is AppearanceKind.FULL else "2nd-half-only"
            print(
                f"  [red][{kind}] {name} played for T{appearance.higher_team}"
                f" in {appearance.home} - {appearance.guest} on {appearance.kickoff}[/]"
            )
        if cm.exempt:
            names = ", ".join(key[0] for key in cm.exempt)
            print(f"  [yellow]Exempt (quota): {names}[/yellow]")


if __name__ == "__main__":
    app = doctyper.DocTyper()
    app.command()(main)
    app()
