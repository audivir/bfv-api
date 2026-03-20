"""Example of how to use the bfv_api to get the standings of a team."""

# ruff: noqa: N815
from __future__ import annotations

import contextlib
import logging
from collections import defaultdict
from datetime import date, datetime
from functools import total_ordering
from typing import Annotated, NoReturn
from zoneinfo import ZoneInfo

import doctyper
from ordered_enum import OrderedEnum
from pydantic import BaseModel, Field
from rich import print  # noqa: A004

from bfv_api import BFV, BFVMatch
from bfv_api.bfv import CompetitionLevel, EventType, MatchReport, MatchTeamInfo, StaffelInfo

logger = logging.getLogger()

MIN_TEAMS = 2
MIN_GAMES = 2
MIN_DAYS = 15
HALFTIME_MINUTE = 45
KA_PLAYER = "k.A.", "NPI_1234567890123456789012345678"
ILLEGAL = "red", "ILLEGAL"
PROB_LEGAL = "yellow", "PROBABLY LEGAL"
LEGAL = "yellow", "LEGAL"


class RomanNumeral(OrderedEnum):
    """Ordered Roman numerals from zero to nine."""

    zero = ""
    one = "I"
    two = "II"
    three = "III"
    four = "IV"
    five = "V"
    six = "VI"
    seven = "VII"
    eight = "VIII"
    nine = "IX"


@total_ordering
class TeamSort(BaseModel):
    """Sort teams on their level and if they are equal on the roman numeral."""

    level: CompetitionLevel
    name: str

    @staticmethod
    def _get_chunk(name: str) -> str:
        chunks = name.split()
        for repl in ("zg.", "zurückgezogen", "B9", "|"):
            with contextlib.suppress(ValueError):
                chunks.remove(repl)
            with contextlib.suppress(ValueError):
                chunks.remove(f"({repl})")
        return chunks[-1]

    def __lt__(self, obj: object) -> bool:
        if not isinstance(obj, type(self)):
            return NotImplemented
        if self == obj:
            return False
        if self.level != obj.level:
            return self.level < obj.level  # type: ignore[no-any-return]
        chunk = self._get_chunk(self.name)
        chunk_numeral = RomanNumeral.zero
        if chunk:
            with contextlib.suppress(ValueError):
                chunk_numeral = RomanNumeral(chunk)
        obj_chunk = self._get_chunk(obj.name)
        obj_chunk_numeral = RomanNumeral.zero
        if obj_chunk:
            with contextlib.suppress(ValueError):
                obj_chunk_numeral = RomanNumeral(obj_chunk)
        if chunk_numeral == obj_chunk_numeral:
            raise ValueError(f"Same roman numeral for {self} and {obj}")
        return chunk_numeral > obj_chunk_numeral  # type: ignore[no-any-return] # team III is lower than team II


class PlayerStatus(BaseModel):
    """Information when a player was last used."""

    higher_team: int
    match_date: date
    first_half: bool
    sat_out_games: dict[int, int] = Field(default_factory=dict)
    is_pre_winter: bool = False


class PlayersMatch(BaseModel):
    """Match object including information about the players used."""

    team: int
    matchId: str
    competitionName: str
    kickoff: datetime
    homeTeam: str
    homeTeamId: str
    guestTeam: str
    guestTeamId: str
    players: dict[tuple[str, str], tuple[bool, int | None]]


def missing_value(key: str) -> NoReturn:
    """Raise an ValueError that a value is missing."""
    raise ValueError(f"Missing value for {key}")


def get_team_info(match_report: MatchReport, club_id: str) -> MatchTeamInfo:
    """Get the team info corresponding to the club id."""
    match_report_info = match_report.matchReportInfo
    if not match_report_info:
        raise ValueError("No match report info")
    if match_report.homeTeamClubId == club_id:
        if home := match_report_info.home:
            return home
        raise ValueError("No information about home team")
    if match_report.guestTeamClubId == club_id:
        if guest := match_report_info.guest:
            return guest
        raise ValueError("No information about guest team")
    raise ValueError("Could not find team by id")


def get_matches_with_players(team_id: str, team_ix: int) -> list[PlayersMatch]:
    """Get a match object including information about the players used."""
    matches_result = BFV.get_team_matches(team_id)
    played_matches: list[BFVMatch] = [m for m in matches_result.data.matches if m.parsed_result]
    club_id = BFV.get_club_info_from_team(team_id).data.club.id

    matches_with_players: list[PlayersMatch] = []
    for m in played_matches:
        if m.competitionType != "Meisterschaften":
            continue
        if not m.kickoffTime:
            raise ValueError("No kickoff time provided")
        try:
            report: MatchReport = BFV.get_match_report(m.matchId).data
            team_info = get_team_info(report, club_id)
            players: dict[tuple[str, str], tuple[bool, int | None]] = {
                (p.name, p.playerInfo.id): (p.substitute, None) for p in team_info.players
            }
            for event in team_info.matchEvents:
                if event.type != EventType.SUBSTITUTE_IN:
                    continue
                if not event.player:
                    raise ValueError("No substituted player")  # noqa: TRY301
                key = (event.player.name, event.player.playerInfo.id)
                if value := players.get(key):
                    substitute, prev_minute = value
                    players[key] = (substitute, min(prev_minute or 1000, event.minute))
                else:
                    raise ValueError("Substituted player not in available player list")  # noqa: TRY301
        except ValueError:
            print(f"Failed to parse match {m.guestTeamName} - {m.guestTeamName}")
            continue

        matches_with_players.append(
            PlayersMatch(
                team=team_ix,
                matchId=m.matchId,
                competitionName=m.competitionName,
                kickoff=datetime.strptime(
                    f"{m.kickoffDate} {m.kickoffTime}", "%d.%m.%Y %H:%M"
                ).astimezone(ZoneInfo("Europe/Berlin")),
                homeTeam=m.homeTeamName,
                homeTeamId=m.homeTeamPermanentId or missing_value("homeTeamPermanentId"),
                guestTeam=m.guestTeamName,
                guestTeamId=m.guestTeamPermanentId or missing_value("guestTeamPermanentId"),
                players=players,
            )
        )
    return matches_with_players


def check_for_ineligible_players(first_team_id: str, *team_ids: str) -> None:  # noqa: C901, PLR0912, PLR0915
    """Print which player were ineligible but used anyways.

    Args:
        first_team_id: BFV team ID of the first team.
        team_ids: BFV team IDs of a single club in descending order. The order will not be checked!
    """
    if not team_ids:
        print("[green bold]Only a single team provided. No violations possible![/green bold]")
        return

    compound_id = BFV.get_team_matches(first_team_id).data.team.compoundId
    competition = BFV.get_competition(compound_id).data
    staffel_info = StaffelInfo.from_model(competition)

    if (staffel_info.competitionType, staffel_info.teamType) != ("Meisterschaften", "Herren"):
        raise ValueError(f"Currently only Herren Meisterschaften supported: {staffel_info}")

    if staffel_info.competitionLevel > CompetitionLevel.bayernliga:
        raise ValueError("Currently supports only clubs at or below Bayernliga")

    team_ids = (first_team_id, *team_ids)

    all_matches: list[PlayersMatch] = []
    for team_ix, team_id in enumerate(team_ids, start=1):
        all_matches.extend(get_matches_with_players(team_id, team_ix))

    all_matches = sorted(all_matches, key=lambda m: m.kickoff)

    allowed_violations = 1 if staffel_info.competitionLevel <= CompetitionLevel.kreisliga else 0  # type: ignore[operator]

    player_status: dict[tuple[str, str], dict[int, PlayerStatus]] = defaultdict(dict)
    last_team_match: dict[int, date] = {}
    first_post_winter_match: dict[int, date] = {}

    for match in all_matches:
        match_date = match.kickoff.date()
        current_team = match.team

        # Retroactively manage winter break detection based on year rollover
        if current_team in last_team_match and match_date.year > last_team_match[current_team].year:
            first_post_winter_match[current_team] = match_date
            last_date = last_team_match[current_team]
            for statuses in player_status.values():
                for higher_team, status in statuses.items():
                    if higher_team == current_team and status.match_date == last_date:
                        status.is_pre_winter = True

        used_players = {
            k
            for k, (substitute, substituted) in match.players.items()
            if not substitute or substituted is not None
        }

        # evaluate restrictions against higher teams
        first_half_violations: dict[tuple[str, str], tuple[PlayerStatus, int]] = {}
        second_half_players: dict[tuple[str, str], tuple[PlayerStatus, int]] = {}
        ka_player_first = False
        ka_player_sec = False
        for player_key in used_players:
            best_ban_status: PlayerStatus | None = None
            best_sec_status: PlayerStatus | None = None
            days_banned, days_sec = 0, 0

            for higher_team, status in player_status.get(player_key, {}).items():
                if higher_team >= current_team:
                    continue  # strictly from higher to lower teams

                reference_date = status.match_date
                if status.is_pre_winter and higher_team in first_post_winter_match:
                    reference_date = first_post_winter_match[higher_team]

                days_elapsed = (match_date - reference_date).days

                if status.first_half:
                    sat_out = status.sat_out_games.get(current_team, 0)
                    if days_elapsed <= MIN_DAYS and sat_out < MIN_GAMES:
                        best_ban_status, days_banned = status, days_elapsed
                elif days_elapsed <= MIN_DAYS:
                    best_sec_status, days_sec = status, days_elapsed

            if best_ban_status:
                if player_key == KA_PLAYER:
                    ka_player_first = True
                first_half_violations[player_key] = (best_ban_status, days_banned)
            elif best_sec_status:
                if player_key == KA_PLAYER:
                    ka_player_sec = True
                second_half_players[player_key] = (best_sec_status, days_sec)

        over_limit_count = max(0, len(second_half_players) - 5)
        total_violations = len(first_half_violations) + over_limit_count

        if total_violations > 0:
            ka_affected = ka_player_first or (over_limit_count and ka_player_sec)
            overhead = total_violations - allowed_violations
            state_color, state_str = (
                ILLEGAL
                if overhead > 1
                else PROB_LEGAL
                if overhead == 1 and ka_affected
                else ILLEGAL
                if overhead == 1
                else LEGAL
            )
            print(
                f"[{state_color} bold]{state_str} Violations found for"
                f" {match.homeTeam} - {match.guestTeam} ({match_date})[/]"
            )
            if ka_affected:
                print(
                    "  [yellow underline]k.A. in lineup might mess up with violation detection[/yellow underline]"  # noqa: E501
                )
            for violating_key, (st, days_elapsed) in first_half_violations.items():
                name, _ = violating_key
                output = (
                    f"  [{state_color}][1st Half Ban]"
                    f" {name} last used in T{st.higher_team}: {st.match_date}"
                    f" (Sat out: {st.sat_out_games.get(current_team, 0)}, {days_elapsed} days ago)"
                )
                if st.is_pre_winter:
                    output += " [Winter Break Rule Applied]"
                print(output + "[/]")

            if over_limit_count > 0:
                print(
                    f"[{state_color}]  [2nd Half Quota Exceeded] {len(second_half_players)}"
                    " players used from 2nd half of higher teams (Max allowed: 5).[/]"
                )
                for p_key, (st, days_elapsed) in second_half_players.items():
                    name, _ = p_key
                    print(
                        f"[{state_color}]    - {name} last used in T{st.higher_team}: {st.match_date} ({days_elapsed} days ago)[/]"  # noqa: E501
                    )
        else:
            print(f"[green]No violations for {match.homeTeam} - {match.guestTeam}[/green]")

        # update sat_out_games for players who did NOT play in this match
        for player_key, team_statuses in player_status.items():
            if player_key not in used_players:
                for higher_team, status in team_statuses.items():
                    if higher_team < current_team and status.first_half:
                        status.sat_out_games[current_team] = (
                            status.sat_out_games.get(current_team, 0) + 1
                        )

        # add/update deployments
        for player_key in used_players:
            substitute, substituted = match.players[player_key]
            is_first_half = bool(not substitute or (substituted and substituted <= HALFTIME_MINUTE))
            player_status[player_key][current_team] = PlayerStatus(
                higher_team=current_team, match_date=match_date, first_half=is_first_half
            )

        last_team_match[current_team] = match_date


def find_teams(club_id: str, raw_pattern: str | None) -> list[str] | None:
    """Find the Herren Meisterschaften teams of a club.

    Args:
        club_id: BFV club ID.
        raw_pattern: Regex pattern to match the team name. If None, the club name will be used.
    """
    club_info = BFV.get_club_info(club_id).data
    club_name = club_info.club.name
    pattern = raw_pattern or club_name

    print(f"[bold blue]=== {club_name} ===[/bold blue]")

    matches = BFV.get_club_matches(club_id, match_type="team").data.matches
    teams: set[tuple[str, str, str]] = set()
    for m in matches:
        if m.teamType != "Herren" or m.competitionType != "Meisterschaften":
            continue
        team_infos = m.select_team(pattern)
        if not team_infos:
            continue
        this_team = team_infos[1]
        if not this_team.teamPermanentId:
            raise ValueError("Team ID missing")
        teams.add((m.compoundId, this_team.teamName, this_team.teamPermanentId))

    if not teams:
        print(
            f"[bold red]No teams found, provide a{' different' if raw_pattern else ''} pattern[/bold red]"  # noqa: E501
        )
        return None

    full_teams: list[tuple[CompetitionLevel, str, str]] = []
    for team in teams:
        staffel_info = StaffelInfo.from_model(BFV.get_competition(team[0]).data)
        full_teams.append((staffel_info.competitionLevel, *team[1:]))

    full_teams = sorted(full_teams, key=lambda t: TeamSort(level=t[0], name=t[1]), reverse=True)

    for team_ix, full_team in enumerate(full_teams, start=1):
        print(f"[yellow]Found {full_team[1]} (T{team_ix}) playing in {full_team[0].value}[/yellow]")

    return [t[2] for t in full_teams]


def main(club_id: str, pattern: Annotated[str | None, doctyper.Argument()] = None) -> None:
    """Check if any ineligible players were used according to the terms of the BFV.

    Args:
        club_id: BFV club ID
        pattern: Regex pattern to match team names to (i.e., the club name)
    """
    logger.warning("End of season restrictions not implemented yet")
    team_ids = find_teams(club_id, pattern)
    if not team_ids:
        raise SystemExit(1)

    check_for_ineligible_players(*team_ids)


if __name__ == "__main__":
    app = doctyper.DocTyper()
    app.command()(main)
    app()
