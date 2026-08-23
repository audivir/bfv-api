"""Retrieve data from BFV API."""

# ruff: noqa: N806, N815
from __future__ import annotations

import logging
import re
from enum import IntEnum
from pathlib import Path
from typing import Generic, Literal, NamedTuple, Protocol, TypeVar

import msgspec
from mxhttp import SyncConsumer, get
from ordered_enum import OrderedEnum
from typing_extensions import ParamSpec, Self

logger = logging.getLogger(__name__)

DataT = TypeVar("DataT")
P = ParamSpec("P")
R = TypeVar("R")

CompetitionT = Literal[
    "Meisterschaften",
    "Freundschaftsspiele",
    "Pokale",
    "Turniere",
    "Hallenturniere",
    "Hallenturniere (Futsal)",
    "Auswahlspiele",
]

TeamT = Literal[
    "Frauen",
    "B-Juniorinnen",
    "C-Juniorinnen",
    "D-Juniorinnen",
    "E-Juniorinnen",
    "Herren Ü60",
    "Herren Ü50",
    "Herren Ü40",
    "Herren Ü45",
    "Herren Ü32",
    "Herren",
    "A-Junioren",
    "B-Junioren",
    "C-Junioren",
    "D-Junioren",
    "E-Junioren",
    "F-Junioren",
    "U14 Junioren",
    "U13 Junioren",
    "Freizeitsport Herren",
]


class CompetitionLevel(OrderedEnum):
    """Defines competition levels for Bavarian football."""

    kreisfreundschaftsspiele = "Kreisfreundschaftsspiele"
    bezirksfreundschaftsspiele = "Bezirksfreundschaftsspiele"
    landesfreundschaftsspiele = "Landesfreundschaftsspiele"

    kreisturnier = "Kreisturnier"
    kreispokal = "Kreispokal"
    verbandspokal = "Verbands-Pokal"

    kinderfussball = "Kinderfußball"  # youth level.
    gruppe = "Gruppe"  # youth level.
    foerderliga = "Förderliga"  # youth level.
    c_klasse = "C Klasse"
    b_klasse = "B Klasse"
    a_klasse = "A Klasse"
    kreisklasse = "Kreisklasse"
    kreisliga = "Kreisliga"
    bezirksliga = "Bezirksliga"
    bezirksoberliga = "Bezirksoberliga"  # youth level.
    landesliga = "Landesliga"
    bayernliga = "Bayernliga"
    regionalliga = "Regionalliga Bayern"
    second_bundesliga = "2.Bundesliga"
    bundesliga = "Bundesliga"


class EventType(IntEnum):
    """Defines categories of match events."""

    SUBSTITUTE_IN = -2
    SUBSTITUTE_OUT = -1
    YELLOW = 2
    RED = 3
    SECOND_YELLOW = 4
    GOAL = 7
    OWN_GOAL = 8
    PENALTY_GOAL = 9
    TIME_PENALTY = 13


class CompetitionType(IntEnum):
    """Defines categories of competition types."""

    Meisterschaften = 1
    Hallenturniere = 2
    Freundschaftsspiele = 70
    Pokale = 308
    Turniere = 300


class Team(msgspec.Struct):
    """Encapsulates team data from BFV API."""

    permanentId: str
    name: str
    typeName: TeamT
    seasonId: str
    clubId: str
    clubName: str
    compoundId: str
    competitionName: str
    competitionBreadcrumb: str


class TeamInfo(NamedTuple):
    """Encapsulates data for a single team."""

    teamName: str
    teamPermanentId: str | None
    clubId: str | None
    logoPrivate: bool


class Match(msgspec.Struct):
    """Encapsulates match data from BFV API."""

    matchId: str
    compoundId: str
    competitionName: str
    competitionType: CompetitionT
    teamType: TeamT
    kickoffDate: str
    kickoffTime: str | None
    homeTeamName: str
    homeTeamPermanentId: str | None
    homeClubId: str | None
    homeLogoPrivate: bool
    guestTeamName: str
    guestTeamPermanentId: str | None
    guestClubId: str | None
    guestLogoPrivate: bool
    result: str
    tickerMatchId: str | None
    prePublished: bool | None = None
    clubTeamNumber: int | None = None

    @property
    def parsed_result(self) -> tuple[int, int] | None:
        """Parse result string into tuple of integers."""
        return parse_result(self)

    def select_team(self, pattern: str) -> tuple[Literal[0, 1], TeamInfo, TeamInfo] | None:
        """Select team info based on regex pattern matching team name.

        Returns:
            Tuple containing index of matched team, matched team info, and opposing team info.
        """
        home = TeamInfo(
            self.homeTeamName, self.homeTeamPermanentId, self.homeClubId, self.homeLogoPrivate
        )
        guest = TeamInfo(
            self.guestTeamName, self.guestTeamPermanentId, self.guestClubId, self.guestLogoPrivate
        )
        teams = f"{self.homeTeamName} - {self.guestTeamName}"
        matches_home = re.search(pattern, self.homeTeamName)
        matches_guest = re.search(pattern, self.guestTeamName)
        if matches_home and matches_guest:
            raise ValueError(f"Pattern ({pattern}) matches both teams: {teams}")
        if matches_home:
            return 0, home, guest
        if matches_guest:
            return 1, guest, home
        logger.warning("Pattern (%s) matches no team: %s", pattern, teams)
        return None


class ShortMatches(msgspec.Struct):
    """Encapsulates short match data from BFV API."""

    matches: list[Match]
    actualMatchId: str


class Matches(ShortMatches):
    """Encapsulates match data from BFV API."""

    team: Team
    actualTickeredMatchId: str | None


class Club(msgspec.Struct):
    """Encapsulates club data from BFV API."""

    id: str
    name: str
    logoUrl: str
    logoPublic: bool


class ClubInfo(msgspec.Struct):
    """Encapsulates club information from BFV API."""

    club: Club
    number: str


class Season(msgspec.Struct):
    """Encapsulates season data from BFV API."""

    id: str
    name: str


class ShortTeam(msgspec.Struct):
    """Encapsulates team data from BFV API."""

    permanentId: str
    name: str | None


class Player(msgspec.Struct):
    """Encapsulates player data from BFV API."""

    test: str


class PlayerInfo(msgspec.Struct):
    """Encapsulates player data from BFV API."""

    photoUrlThumb: str
    photoUrlStamp: str
    photoUrlImage: str

    @property
    def id(self) -> str:
        """Return player ID."""
        return Path(self.photoUrlImage).stem


class MatchPlayer(msgspec.Struct):
    """Encapsulates player data from BFV API."""

    name: str
    number: int
    captain: bool
    keeper: bool
    substitute: bool
    playerInfo: PlayerInfo


class Squad(msgspec.Struct):
    """Encapsulates squad data from BFV API."""

    public: bool
    season: Season
    team: ShortTeam
    players: list[Player]


class Venue(msgspec.Struct):
    """Encapsulates venue data from BFV API."""

    type: Literal[0, 1, 3]
    typeName: Literal["Rasenplatz", "Kunstrasenplatz"] | None
    name: str | None
    street: str | None
    zipCode: str | None
    city: str | None


class MatchEvent(msgspec.Struct):
    """Encapsulates match event data from BFV API."""

    minute: int
    additionalTimeMinute: int
    type: EventType
    sortPos: int
    player: MatchPlayer | None


class MatchTeamInfo(msgspec.Struct):
    """Encapsulates team data from BFV API."""

    trainer: str
    players: list[MatchPlayer]
    matchEvents: list[MatchEvent]


class MatchReportInfo(msgspec.Struct):
    """Encapsulates match report data from BFV API."""

    home: MatchTeamInfo | None
    guest: MatchTeamInfo | None
    endTime: str | None
    extraTimeFirstHalf: int | None
    extraTimeSecondHalf: int | None
    spectators: int | None


class MatchReport(msgspec.Struct):
    """Encapsulates match report data from BFV API."""

    staffelzusatz: str
    matchId: str
    result: str
    startDate: str
    startTime: str
    leageName: str
    season: str
    homeTeamName: str
    guestTeamName: str | None
    homeTeamClubId: str | None
    guestTeamClubId: str | None
    compoundId: str
    matchNr: str
    prevMatchId: str | None
    nextMatchId: str | None
    venue: Venue
    referee: str
    assistant1: str
    assistant2: str
    forthOfficial: str | None
    spielTickerId: str | None
    tickerMatchId: str | None
    matchReportInfo: MatchReportInfo | None
    adCode: str

    @property
    def parsed_result(self) -> tuple[int, int] | None:
        """Parse result string into tuple of integers."""
        return parse_result(self)


class StandingsTeam(msgspec.Struct):
    """Encapsulates team data within league standings."""

    seasonId: str | None
    seasonName: str
    permanentId: str | None
    competitionId: str
    rang: str
    teamname: str
    anzspiele: int
    punkte: int
    s: int
    u: int
    n: int
    tore: str
    tordiff: str
    aufab: int | None
    verzicht: int
    clubId: str | None


class MatchDay(msgspec.Struct):
    """Encapsulates match day metadata."""

    spieltag: str
    bezeichnung: str


class HasStaffelzusatz(Protocol):
    """Interface for objects providing a staffelzusatz attribute."""

    staffelzusatz: str


class StaffelInfo(msgspec.Struct):
    """Encapsulates staffel metadata."""

    competitionType: CompetitionT
    teamType: TeamT
    competitionLevel: CompetitionLevel
    competitionArea: str

    @classmethod
    def from_model(cls, model: HasStaffelzusatz) -> Self:
        """Create staffel information from staffelzusatz attribute."""
        competitionType, teamType, competitionLevel, competitionArea = model.staffelzusatz.split(
            " | "
        )
        return msgspec.convert(
            {
                "competitionType": competitionType,
                "teamType": teamType,
                "competitionLevel": competitionLevel,
                "competitionArea": competitionArea,
            },
            cls,
        )


class Competition(msgspec.Struct):
    """Encapsulates competition metadata and schedule."""

    saison: str
    compoundId: str
    staffelId: str
    staffelname: str
    staffelzusatz: str
    staffelnr: str
    staffelTypId: CompetitionType
    staffelTypName: CompetitionT
    adCode: str
    anzAufsteiger: int
    anzAufsteigerq: int
    anzAbsteigerq: int
    anzAbsteiger: int
    stLiveticker: bool
    matches: list[Match]
    tabelle: list[StandingsTeam] | None
    spieltage: list[MatchDay]
    selSpieltag: str
    actualMatchDay: str

    def __post_init__(self) -> None:
        """Validate consistency between staffel type name and ID."""
        if self.staffelTypName != self.staffelTypId.name:
            raise ValueError("Competition mismatch")


class TopScorerPlayer(msgspec.Struct):
    """Encapsulates statistics and metadata for a top-scoring player."""

    playerImage: str
    playerImageStamp: str
    playerImageCopyright: str | None
    name: str
    team: ShortTeam
    rank: int
    goals: int


class TopScorer(msgspec.Struct):
    """Encapsulates top scorer data for a specific competition."""

    compoundId: str
    competitionName: str
    adCode: str
    scorers: list[TopScorerPlayer]


class Standings(msgspec.Struct):
    """Encapsulates league standings and team rankings for a competition."""

    compoundId: str
    competitionName: None
    tabelle: list[StandingsTeam]


class Response(msgspec.Struct, Generic[DataT]):
    """Encapsulates a response from BFV API."""

    state: int
    message: str | None
    data: DataT


def parse_result(match: Match | MatchReport, _parse: bool = True) -> tuple[int, int] | None:  # noqa: C901, PLR0911
    """Parse match result into tuple of integers."""
    result = match.result
    home = match.homeTeamName.strip()
    if not match.guestTeamName or not result or result == "Abse.":
        # game not yet played, cancelled, or missing opponent.
        return None
    if result == "Abbr.":
        # game interrupted without verdict.
        return -1, -1
    guest = match.guestTeamName.strip()
    if result == "n.an.":
        if home[0] == "(" and home[-1] == ")":
            return 0, 2
        if guest[0] == "(" and guest[-1] == ")":
            return 2, 0
        raise ValueError(f"Invalid n.an. result string for {home} vs {guest}: {result}")
    if result.endswith("nE"):
        match.result = result.removesuffix("nE")
        return parse_result(match)
    if "w" in result.casefold() or "u" in result.casefold():
        if not _parse:
            raise ValueError(f"Invalid result string for {home} vs {guest}: {result}")
        try:
            match.result = re.split("w|u", result.casefold(), maxsplit=1)[0].strip()
            return parse_result(match, _parse=False)
        except ValueError:
            match.result = result
            raise
    try:
        home_score, guest_score = result.split(":")
        return int(home_score), int(guest_score)
    except ValueError as e:
        raise ValueError(f"Invalid result string for {home} vs {guest}: {result}") from e


class BFVConsumer(SyncConsumer):
    """Client for BFV API."""

    @get("/api/service/widget/v1/team/{team_id}/matches")
    def get_team_matches(self, team_id: str) -> Response[Matches]:  # type: ignore[empty-body]
        """Retrieve matches for specified team."""

    @get("/api/service/widget/v1/team/{team_id}/squad")
    def get_team_squad(self, team_id: str) -> Response[Squad]:  # type: ignore[empty-body]
        """Retrieve squad for specified team."""

    @get("/rest/competitioncontroller/competition/id/{competition_id}")
    def get_competition(self, competition_id: str) -> Response[Competition]:  # type: ignore[empty-body]
        """Retrieve competition for specified competition ID."""

    @get("/rest/competitioncontroller/competition/id/{competition_id}/matchday/{match_day}")
    def get_competition_for_match_day(  # type: ignore[empty-body]
        self, competition_id: str, match_day: int
    ) -> Response[Competition]:
        """Retrieve competition for specified match day."""

    @get("/api/service/widget/v1/competition/{competition_id}/topscorer")
    def get_competition_top_scorer(self, competition_id: str) -> Response[TopScorer | None]:  # type: ignore[empty-body]
        """Retrieve top scorer for specified competition."""

    @get("/rest/competitioncontroller/competition/table/{standings_type}/id/{competition_id}")
    def get_competition_standings(  # type: ignore[empty-body]
        self,
        competition_id: str,
        standings_type: Literal["", "home", "away", "firsthalfseason", "secondhalfseason"] = "",
    ) -> Response[Standings]:
        """Retrieve standings for specified competition."""

    @get("/rest/clubcontroller/fixtures/id/{club_id}/matchtype/{match_type}")
    def get_club_matches(  # type: ignore[empty-body]
        self, club_id: str, match_type: Literal["all", "home", "away", "team"] = "all"
    ) -> Response[ShortMatches]:
        """Retrieve matches for specified club."""

    @get("/api/service/widget/v1/club/{club_id}/info")
    def get_club_info(self, club_id: str) -> Response[ClubInfo]:  # type: ignore[empty-body]
        """Retrieve information for specified club."""

    @get("/api/service/widget/v1/club/info?teamPermanentId={team_id}")
    def get_club_info_from_team(self, team_id: str) -> Response[ClubInfo]:  # type: ignore[empty-body]
        """Retrieve club information for specified team ID."""

    @get("/rest/matchcontroller/matchreport/id/{match_id}")
    def get_match_report(self, match_id: str) -> Response[MatchReport]:  # type: ignore[empty-body]
        """Retrieve report for specified match."""


BFV = BFVConsumer(base_url="https://widget-prod.bfv.de")


def test_all() -> None:
    """Verify all API endpoints."""
    fcbayern_u13 = "01BKG17M3S000000VV0AG811VTNTKEKF"

    result = BFV.get_club_info_from_team(fcbayern_u13).data
    club_id = result.club.id

    matches = BFV.get_club_matches(club_id).data.matches
    unique_competitions = {match.compoundId for match in matches}
    for ix, comp in enumerate(unique_competitions):
        comp_data = BFV.get_competition(comp).data
        standings = BFV.get_competition_standings(comp).data
        top_scorer = BFV.get_competition_top_scorer(comp).data
        if ix == 0:
            print(comp_data, standings, top_scorer)  # noqa: T201
    for ix, match in enumerate(matches):
        report = BFV.get_match_report(match.matchId)
        if ix == 0:
            print(report)  # noqa: T201
