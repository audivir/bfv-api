"""Shared test factories for bfv_api tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from bfv_api.bfv import (
    CompetitionT,
    EventType,
    Match,
    MatchEvent,
    MatchPlayer,
    MatchReport,
    MatchReportInfo,
    MatchTeamInfo,
    PlayerInfo,
    TeamT,
    Venue,
)
from bfv_api.ineligibility import PlayersMatch

if TYPE_CHECKING:
    from datetime import datetime


def make_match(  # noqa: PLR0913
    *,
    result: str = "2:1",
    home_team_name: str = "Home",
    guest_team_name: str = "Guest",
    competition_type: CompetitionT = "Meisterschaften",
    team_type: TeamT = "Herren",
    home_team_permanent_id: str | None = "H1",
    guest_team_permanent_id: str | None = "G1",
    kickoff_date: str = "01.01.2026",
    kickoff_time: str | None = "15:00",
) -> Match:
    return Match(
        matchId="M1",
        compoundId="C1",
        competitionName="Kreisliga",
        competitionType=competition_type,
        teamType=team_type,
        kickoffDate=kickoff_date,
        kickoffTime=kickoff_time,
        homeTeamName=home_team_name,
        homeTeamPermanentId=home_team_permanent_id,
        homeClubId="HC1",
        homeLogoPrivate=False,
        guestTeamName=guest_team_name,
        guestTeamPermanentId=guest_team_permanent_id,
        guestClubId="GC1",
        guestLogoPrivate=False,
        result=result,
        tickerMatchId=None,
    )


def make_venue(*, venue_type: Literal[0, 1, 3] = 0) -> Venue:
    return Venue(type=venue_type, typeName=None, name=None, street=None, zipCode=None, city=None)


def make_players_match(
    *,
    team: int = 1,
    kickoff: datetime,
    players: dict[tuple[str, str], tuple[bool, int | None]] | None = None,
    home_team: str = "Home",
    guest_team: str = "Guest",
) -> PlayersMatch:
    return PlayersMatch(
        team=team,
        matchId="M1",
        competitionName="Kreisliga",
        kickoff=kickoff,
        homeTeam=home_team,
        homeTeamId="H1",
        guestTeam=guest_team,
        guestTeamId="G1",
        players=players or {},
    )


def make_match_player(
    *, name: str = "Player", substitute: bool = False, photo_id: str = "1"
) -> MatchPlayer:
    return MatchPlayer(
        name=name,
        number=1,
        captain=False,
        keeper=False,
        substitute=substitute,
        playerInfo=PlayerInfo(
            photoUrlThumb="", photoUrlStamp="", photoUrlImage=f"https://example.com/{photo_id}.jpg"
        ),
    )


def make_match_event(
    *, event_type: EventType, minute: int = 10, player: MatchPlayer | None = None
) -> MatchEvent:
    return MatchEvent(
        minute=minute, additionalTimeMinute=0, type=event_type, sortPos=0, player=player
    )


def make_match_team_info(
    *,
    players: list[MatchPlayer] | None = None,
    events: list[MatchEvent] | None = None,
) -> MatchTeamInfo:
    return MatchTeamInfo(trainer="", players=players or [], matchEvents=events or [])


def make_match_report(
    *,
    home_club_id: str | None = None,
    guest_club_id: str | None = None,
    home_info: MatchTeamInfo | None = None,
    guest_info: MatchTeamInfo | None = None,
    has_report_info: bool = True,
) -> MatchReport:
    return MatchReport(
        staffelzusatz="",
        matchId="M1",
        result="1:0",
        startDate="",
        startTime="",
        leageName="",
        season="",
        homeTeamName="Home",
        guestTeamName="Guest",
        homeTeamClubId=home_club_id,
        guestTeamClubId=guest_club_id,
        compoundId="",
        matchNr="",
        prevMatchId=None,
        nextMatchId=None,
        venue=make_venue(),
        referee="",
        assistant1="",
        assistant2="",
        forthOfficial=None,
        spielTickerId=None,
        tickerMatchId=None,
        matchReportInfo=MatchReportInfo(
            home=home_info,
            guest=guest_info,
            endTime=None,
            extraTimeFirstHalf=None,
            extraTimeSecondHalf=None,
            spectators=None,
        )
        if has_report_info
        else None,
        adCode="",
    )
