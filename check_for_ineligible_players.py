"""Example of how to use the bfv_api to get the standings of a team."""

# ruff: noqa: T201,N815
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import NoReturn
from zoneinfo import ZoneInfo

from ordered_enum import OrderedEnum
from pydantic import BaseModel, Field

from bfv_api import BFV, BFVMatch
from bfv_api.bfv import EventType, MatchReport, MatchTeamInfo

# currently supports only §34 2

MIN_TEAMS = 2
MIN_GAMES = 2
MIN_DAYS = 15
HALFTIME_MINUTE = 45


class CompetitionLevel(OrderedEnum):
    """All levels in Bavarian football."""

    c_klasse = "C Klasse"
    b_klasse = "B Klasse"
    a_klasse = "A Klasse"
    kreisklasse = "Kreisklasse"
    kreisliga = "Kreisliga"
    bezirksliga = "Bezirksliga"
    landesliga = "Landesliga"
    bayernliga = "Bayernliga"
    regionalliga = "Regionalliga Bayern"
    second_bundesliga = "2.Bundesliga"
    bundesliga = "Bundesliga"


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


def check_for_ineligible_players(*team_ids: str) -> None:  # noqa: C901, PLR0912, PLR0915
    """Print which player were ineligible but used anyways."""
    if len(team_ids) < MIN_TEAMS:
        raise ValueError(f"At least {MIN_TEAMS} teams necessary")

    # check where the first team plays
    comp_id = BFV.get_team_matches(team_ids[0]).data.team.compoundId
    comp_type, comp_sex, comp_level, dummy_comp_area = BFV.get_competition(
        comp_id
    ).data.staffelzusatz.split(" | ")

    if (comp_type, comp_sex) != ("Meisterschaften", "Herren"):
        raise ValueError(f"Currently only Herren supported: {comp_type} {comp_sex}")

    if CompetitionLevel(comp_level) > CompetitionLevel.bayernliga:
        raise ValueError("Currently supports only clubs at or below Bayernliga")

    all_matches: list[PlayersMatch] = []
    for team_ix, team_id in enumerate(team_ids, start=1):
        all_matches.extend(get_matches_with_players(team_id, team_ix))

    all_matches = sorted(all_matches, key=lambda m: m.kickoff)

    allowed_violations = 1 if CompetitionLevel(comp_level) <= CompetitionLevel.kreisliga else 0  # type: ignore[operator]

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

        # 1. Evaluate restrictions against higher teams
        first_half_violations = {}
        second_half_players = {}

        for player_key in used_players:
            is_strictly_banned = False
            is_sec_half_restricted = False
            best_ban_status, best_sec_status = None, None
            days_banned, days_sec = 0, 0

            for higher_team, status in player_status.get(player_key, {}).items():
                if higher_team >= current_team:
                    continue  # Rule applies strictly from higher to lower teams

                reference_date = status.match_date
                if status.is_pre_winter and higher_team in first_post_winter_match:
                    reference_date = first_post_winter_match[higher_team]

                days_elapsed = (match_date - reference_date).days

                if status.first_half:
                    sat_out = status.sat_out_games.get(current_team, 0)
                    if days_elapsed <= MIN_DAYS and sat_out < MIN_GAMES:
                        is_strictly_banned = True
                        best_ban_status, days_banned = status, days_elapsed
                elif days_elapsed <= MIN_DAYS:
                    is_sec_half_restricted = True
                    best_sec_status, days_sec = status, days_elapsed

                # Strict bans supersede 2nd half quotas
                if is_strictly_banned:
                    first_half_violations[player_key] = (best_ban_status, days_banned)
                elif is_sec_half_restricted:
                    second_half_players[player_key] = (best_sec_status, days_sec)

        over_limit_count = max(0, len(second_half_players) - 5)
        total_violations = len(first_half_violations) + over_limit_count

        if total_violations > 0:
            state = "ILLEGAL" if total_violations > allowed_violations else "LEGAL"
            print(
                f"{state} Violations found for {match.homeTeam} - {match.guestTeam} ({match_date})"
            )
            for violating_key, (st, days_elapsed) in first_half_violations.items():
                name, _ = violating_key
                output = (
                    f"  [1st Half Ban] {name} last used in T{st.higher_team}: {st.match_date}"
                    f" (Sat out: {st.sat_out_games.get(current_team, 0)}, {days_elapsed} days ago)"
                )
                if st.is_pre_winter:
                    output += " [Winter Break Rule Applied]"
                print(output)

            if over_limit_count > 0:
                print(
                    f"  [2nd Half Quota Exceeded] {len(second_half_players)}"
                    " players used from 2nd half of higher teams (Max allowed: 5)."
                )
                for p_key, (st, days_elapsed) in second_half_players.items():
                    name, _ = p_key
                    print(
                        f"    - {name} last used in T{st.higher_team}: {st.match_date} ({days_elapsed} days ago)"  # noqa: E501
                    )
        else:
            print(f"No violations for {match.homeTeam} - {match.guestTeam}")

        # 2. Update sat_out_games for players who did NOT play in this match
        for player_key, team_statuses in player_status.items():
            if player_key not in used_players:
                for higher_team, status in team_statuses.items():
                    if higher_team < current_team and status.first_half:
                        status.sat_out_games[current_team] = (
                            status.sat_out_games.get(current_team, 0) + 1
                        )

        # 3. Add/Update deployments
        for player_key in used_players:
            substitute, substituted = match.players[player_key]
            is_first_half = not substitute or (substituted and substituted <= HALFTIME_MINUTE)
            player_status[player_key][current_team] = PlayerStatus(
                higher_team=current_team, match_date=match_date, first_half=is_first_half
            )

        last_team_match[current_team] = match_date


maccabi_2 = "02T8MU6B6G000000VS5489BRVTHNGU03"
maccabi_1 = "023L2KETVK000000VS548985VTNSAQK7"
check_for_ineligible_players(maccabi_1, maccabi_2)

moegeldorf_1 = "016PH7JLPG000000VV0AG811VUDIC8D7"
moegeldorf_2 = "016PJKGN5K000000VV0AG80NVUT1FLRU"
moegeldorf_3 = "01KVCSNG4S000000VV0AG80NVVRC6LS5"
moegeldorf_4 = "02TANAOOSO000000VS5489BRVTHNGU03"
check_for_ineligible_players(moegeldorf_1, moegeldorf_2, moegeldorf_3, moegeldorf_4)
