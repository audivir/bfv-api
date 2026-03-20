"""Example of how to use the bfv_api to get the standings of a team."""

# ruff: noqa: T201,N815
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NoReturn, NamedTuple
from zoneinfo import ZoneInfo

from ordered_enum import OrderedEnum
from pydantic import BaseModel
from pydantic import BaseModel, Field
from bfv_api import BFV, BFVMatch
from bfv_api.bfv import EventType, MatchReport, MatchTeamInfo

# currently supports only §34 2

MIN_GAMES = 2
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

class LastUsed(NamedTuple):
    prev_date: date
    games: dict[int, int]


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


def apply_winter_break_rule(
    key: tuple[str, str], match_date: date, prev_date: date, winter_break_rule: date | None
) -> date:
    """Apply the winter break rule.

    It states that players who played the last match before the winter break
    need to pause two games after the break or 15-days after the first game
    of the first team.
    """
    if not winter_break_rule or prev_date != winter_break_rule:
        return prev_date
    print(f"{key[0]} was used before the winter break, new countdown starting at {match_date}")
    return match_date


def check_for_ineligible_players(*team_ids: str) -> None:  # noqa: C901, PLR0912
    """Print which player were ineligible but used anyways."""
    if len(team_ids) < 2:
        raise ValueError("At least 2 teams necessary")

    # check where the first team plays
    comp_id = BFV.get_team_matches(team_ids[0]).data.team.compoundId
    comp_type, comp_sex, comp_level, dummy_comp_area = BFV.get_competition(
        comp_id
    ).data.staffelzusatz.split(" | ")

    if (comp_type, comp_sex) != ("Meisterschaften", "Herren"):
        raise ValueError("Currently only Herren supported")

    if CompetitionLevel(comp_level) > CompetitionLevel.bayernliga:
        raise ValueError("Currently supports only clubs at or below Bayernliga")

    all_matches: list[PlayersMatch] = []
    for team_ix, team_id in enumerate(team_ids, start=1):
        all_matches.extend(get_matches_with_players(team_id, team_ix))

    all_matches = sorted(all_matches, key=lambda m: m.kickoff)

    ineligible_players: dict[tuple[str, str], tuple[int, date, int]] = {}

    # if a player is used in the first half of a first team match
    # he is banned for the next two matches or 15 days
    #
    #
    allowed_violations = 1 if CompetitionLevel(comp_level) <= CompetitionLevel.kreisliga else 0  # type: ignore[operator]

    # decision / relegation matches currently not implemented
    last_first_team_match: date | None = None
    winter_break_rule_reset: tuple[date, date] | None = None
    for match in all_matches:
        match_date = match.kickoff.date()
        winter_break_rule = (
            last_first_team_match
            if last_first_team_match and match_date.year > last_first_team_match.year
            else None
        )

        if match.team == 1:
            for player_key, (substitute, substituted) in match.players.items():
                if not substitute or (substituted and substituted <= HALFTIME_MINUTE):
                    ineligible_players[player_key] = (match_date, 0)
            if winter_break_rule:  # update date to first first team match
                ineligible_players = {
                    k: (apply_winter_break_rule(k, match_date, prev_date, winter_break_rule), games)
                    for k, (prev_date, games) in ineligible_players.items()
                }
                winter_break_rule_reset = winter_break_rule, match_date

            last_first_team_match = match_date
        elif match.team == 2:  # noqa: PLR2004
            ineligible_players_set = {
                k
                for k, (prev_date, games) in ineligible_players.items()
                if games < MIN_GAMES
                and (
                    (match_date - prev_date) < timedelta(days=15) or prev_date == winter_break_rule
                )
            }
            used_players_set = {
                k
                for k, (substitute, substituted) in match.players.items()
                if not substitute or substituted is not None
            }

            violations = ineligible_players_set & used_players_set

            if violations:
                state = "ILLEGAL" if len(violations) > allowed_violations else "LEGAL"
                print(
                    f"{state} Violations found for {match.homeTeam} - {match.guestTeam} ({match_date})"  # noqa: E501
                )
                for violating_key in violations:
                    name, _ = violating_key
                    prev_date, _ = ineligible_players[violating_key]
                    output = f"  {name} was last used: {prev_date}"
                    if winter_break_rule_reset and prev_date == winter_break_rule_reset[1]:
                        output += f" (or before the winter break: {winter_break_rule_reset[0]})"
                    print(output)
            else:
                print(f"No violations for {match.homeTeam} - {match.guestTeam}")

            ineligible_players = {
                k: (match_date, games + 1) for k, (match_date, games) in ineligible_players.items()
            }

        else:
            raise ValueError(f"Unexpected team: {match.team}")


maccabi_2 = "02T8MU6B6G000000VS5489BRVTHNGU03"
maccabi_1 = "023L2KETVK000000VS548985VTNSAQK7"
check_for_ineligible_players(maccabi_1, maccabi_2)

moegeldorf_1 = "02M9PHV288000000VS5489B1VV4JLPLE"
moegeldorf_2 = "016PJKGN5K000000VV0AG80NVUT1FLRU"
moegeldorf_3 = "01KVCSNG4S000000VV0AG80NVVRC6LS5"
moegeldorf_4 = "02TANAOOSO000000VS5489BRVTHNGU03"
check_for_ineligible_players(moegeldorf_1, moegeldorf_2, moegeldorf_3, moegeldorf_4)
