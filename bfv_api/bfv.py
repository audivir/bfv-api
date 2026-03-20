"""Retrieve data from the BFV API."""

# ruff: noqa: N806, N815
from __future__ import annotations

import logging
import re
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Literal, NamedTuple, Protocol, TypeVar

from doctyper._typing import get_type_hints
from ordered_enum import OrderedEnum
from pydantic import BaseModel, model_validator
from typing_extensions import ParamSpec, Self
from uplink import Consumer, get

if TYPE_CHECKING:
    from collections.abc import Callable

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


def typed_get(endpoint: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Create a typed get method."""

    def _typed_get(func: Callable[P, R]) -> Callable[P, R]:
        """Create a typed get method."""
        # parse string type annotations to python types
        func.__annotations__ = get_type_hints(func)
        return get(endpoint)(func)  # type: ignore[no-any-return]

    return _typed_get


class CompetitionLevel(OrderedEnum):
    """All levels in Bavarian football."""

    kreisfreundschaftsspiele = "Kreisfreundschaftsspiele"
    bezirksfreundschaftsspiele = "Bezirksfreundschaftsspiele"
    landesfreundschaftsspiele = "Landesfreundschaftsspiele"

    kreisturnier = "Kreisturnier"
    kreispokal = "Kreispokal"
    verbandspokal = "Verbands-Pokal"

    kinderfussball = "Kinderfußball"  # JUGEND
    gruppe = "Gruppe"  # JUGEND
    foerderliga = "Förderliga"  # JUGEND
    c_klasse = "C Klasse"
    b_klasse = "B Klasse"
    a_klasse = "A Klasse"
    kreisklasse = "Kreisklasse"
    kreisliga = "Kreisliga"
    bezirksliga = "Bezirksliga"
    bezirksoberliga = "Bezirksoberliga"  # JUGEND
    landesliga = "Landesliga"
    bayernliga = "Bayernliga"
    regionalliga = "Regionalliga Bayern"
    second_bundesliga = "2.Bundesliga"
    bundesliga = "Bundesliga"


class EventType(IntEnum):
    """The type of an event."""

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
    """Enum numbers of different competition types."""

    Meisterschaften = 1
    Hallenturniere = 2
    Freundschaftsspiele = 70
    Pokale = 308
    Turniere = 300


class Team(BaseModel):
    """A team from the BFV API."""

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
    """Information about a single team."""

    teamName: str
    teamPermanentId: str | None
    clubId: str | None
    logoPrivate: bool


class Match(BaseModel):
    """A match from the BFV API."""

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
        """Result string as a tuple of integers."""
        return parse_result(self)

    def select_team(self, pattern: str) -> tuple[Literal[0, 1], TeamInfo, TeamInfo] | None:
        """Select the info of a team based a regex pattern matching the team name.

        Returns:
            A tuple with the index for the parsed result,
            the selected team's info and the other team's info.
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


class ShortMatches(BaseModel):
    """The data from the BFV API."""

    matches: list[Match]
    actualMatchId: str


class Matches(ShortMatches):
    """The data from the BFV API."""

    team: Team
    actualTickeredMatchId: str | None


class Club(BaseModel):
    """A club from the BFV API."""

    id: str
    name: str
    logoUrl: str
    logoPublic: bool


class ClubInfo(BaseModel):
    """The data from the BFV API."""

    club: Club
    number: str


class Season(BaseModel):
    """A season from the BFV API."""

    id: str
    name: str


class ShortTeam(BaseModel):
    """A team from the BFV API."""

    permanentId: str
    name: str | None


class Player(BaseModel):
    """A player from the BFV API."""

    test: str


class PlayerInfo(BaseModel):
    """The data from the BFV API."""

    photoUrlThumb: str
    photoUrlStamp: str
    photoUrlImage: str

    @property
    def id(self) -> str:
        """Player ID."""
        return Path(self.photoUrlImage).stem


class MatchPlayer(BaseModel):
    """A player from the BFV API."""

    name: str
    number: int
    captain: bool
    keeper: bool
    substitute: bool
    playerInfo: PlayerInfo


class Squad(BaseModel):
    """A squad from the BFV API."""

    public: bool
    season: Season
    team: ShortTeam
    players: list[Player]


class Venue(BaseModel):
    """A venue from the BFV API."""

    type: Literal[0, 1, 3]
    typeName: Literal["Rasenplatz", "Kunstrasenplatz"] | None
    name: str | None
    street: str | None
    zipCode: str | None
    city: str | None


class MatchEvent(BaseModel):
    """A match event from the BFV API."""

    minute: int
    additionalTimeMinute: int
    type: EventType
    sortPos: int
    player: MatchPlayer | None


class MatchTeamInfo(BaseModel):
    """A team from the BFV API."""

    trainer: str
    players: list[MatchPlayer]
    matchEvents: list[MatchEvent]


class MatchReportInfo(BaseModel):
    """The data from the BFV API."""

    home: MatchTeamInfo | None
    guest: MatchTeamInfo | None
    endTime: str | None
    extraTimeFirstHalf: int | None
    extraTimeSecondHalf: int | None
    spectators: int | None


class MatchReport(BaseModel):
    """A match report from the BFV API."""

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
        """Result string as a tuple of integers."""
        return parse_result(self)


class StandingsTeam(BaseModel):
    """A team in the standings."""

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


class MatchDay(BaseModel):
    """A match day."""

    spieltag: str
    bezeichnung: str


class HasStaffelzusatz(Protocol):
    """Object with a staffelzusatz attribute."""

    staffelzusatz: str


class StaffelInfo(BaseModel):
    """Information about the staffel."""

    competitionType: CompetitionT
    teamType: TeamT
    competitionLevel: CompetitionLevel
    competitionArea: str

    @classmethod
    def from_model(cls, model: HasStaffelzusatz) -> Self:
        """Create the staffel information from staffelzusatz attribute."""
        competitionType, teamType, competitionLevel, competitionArea = model.staffelzusatz.split(
            " | "
        )
        return cls.model_validate(
            {
                "competitionType": competitionType,
                "teamType": teamType,
                "competitionLevel": competitionLevel,
                "competitionArea": competitionArea,
            }
        )


class Competition(BaseModel):
    """A competition."""

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

    @model_validator(mode="after")
    def validate_competition(self) -> Self:
        """Validate our enum is correct."""
        if self.staffelTypName != self.staffelTypId.name:
            raise ValueError("Competition mismatch")
        return self


class TopScorerPlayer(BaseModel):
    """A player in the top scorer."""

    playerImage: str
    playerImageStamp: str
    playerImageCopyright: str | None
    name: str
    team: ShortTeam
    rank: int
    goals: int


class TopScorer(BaseModel):
    """A top scorer."""

    compoundId: str
    competitionName: str
    adCode: str
    scorers: list[TopScorerPlayer]


class Standings(BaseModel):
    """A standings."""

    compoundId: str
    competitionName: None
    tabelle: list[StandingsTeam]


class Response(BaseModel, Generic[DataT]):
    """A response from the BFV API."""

    state: int
    message: str | None
    data: DataT


def parse_result(match: Match | MatchReport, _parse: bool = True) -> tuple[int, int] | None:
    """Parse the result string into a tuple of integers."""
    result = match.result
    home = match.homeTeamName.strip()
    if not match.guestTeamName or not result or result == "Abse.":
        # game not yet played or cancelled or no opponent
        return None
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


class BFVConsumer(Consumer):  # type: ignore[misc]
    """A Python Client for the BFV API."""

    @typed_get("/api/service/widget/v1/team/{team_id}/matches")
    def get_team_matches(self, team_id: str) -> Response[Matches]:  # type: ignore[empty-body]
        """Retrieves the team's matches."""

    @typed_get("/api/service/widget/v1/team/{team_id}/squad")
    def get_team_squad(self, team_id: str) -> Response[Squad]:  # type: ignore[empty-body]
        """Retrieves the team's squad."""

    @typed_get("/rest/competitioncontroller/competition/id/{competition_id}")
    def get_competition(self, competition_id: str) -> Response[Competition]:  # type: ignore[empty-body]
        """Retrieves the competition for the current match day."""

    @typed_get("/rest/competitioncontroller/competition/id/{competition_id}/matchday/{match_day}")
    def get_competition_for_match_day(  # type: ignore[empty-body]
        self, competition_id: str, match_day: int
    ) -> Response[Competition]:
        """Retrieves the competition for the given match day."""

    @typed_get("/api/service/widget/v1/competition/{competition_id}/topscorer")
    def get_competition_top_scorer(self, competition_id: str) -> Response[TopScorer | None]:  # type: ignore[empty-body]
        """Retrieves the competition's top scorer."""

    @typed_get("/rest/competitioncontroller/competition/table/{standings_type}/id/{competition_id}")
    def get_competition_standings(  # type: ignore[empty-body]
        self,
        competition_id: str,
        standings_type: Literal["", "home", "away", "firsthalfseason", "secondhalfseason"] = "",
    ) -> Response[Standings]:
        """Retrieves the competition's standings."""

    @typed_get("/rest/clubcontroller/fixtures/id/{club_id}/matchtype/{match_type}")
    def get_club_matches(  # type: ignore[empty-body]
        self, club_id: str, match_type: Literal["all", "home", "away", "team"] = "all"
    ) -> Response[ShortMatches]:
        """Retrieves the club's matches."""

    @typed_get("/api/service/widget/v1/club/{club_id}/info")
    def get_club_info(self, club_id: str) -> Response[ClubInfo]:  # type: ignore[empty-body]
        """Retrieves the club's information."""

    @typed_get("/api/service/widget/v1/club/info?teamPermanentId={team_id}")
    def get_club_info_from_team(self, team_id: str) -> Response[ClubInfo]:  # type: ignore[empty-body]
        """Retrieves the club's information from a team ID."""

    @typed_get("/rest/matchcontroller/matchreport/id/{match_id}")
    def get_match_report(self, match_id: str) -> Response[MatchReport]:  # type: ignore[empty-body]
        """Retrieves the match report."""


BFV = BFVConsumer(base_url="https://widget-prod.bfv.de")


def test_all() -> None:
    """Test all endpoints."""
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
