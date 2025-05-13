# %%
from uplink import Consumer, get
from pydantic import BaseModel
from typing import Literal
from enum import IntEnum
import re

TeamT = Literal[
    "Frauen",
    "B-Juniorinnen",
    "C-Juniorinnen",
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
]


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


class Match(BaseModel):
    """A match from the BFV API."""

    matchId: str
    compoundId: str
    competitionName: str
    competitionType: str
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


class Competition(BaseModel):
    """A competition."""

    saison: str
    compoundId: str
    staffelId: str
    staffelname: str
    staffelzusatz: str
    staffelnr: str
    staffelTypId: Literal[1, 70, 300]
    staffelTypName: Literal["Meisterschaften", "Freundschaftsspiele", "Turniere"]
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


class Response[DataT](BaseModel):
    """A response from the BFV API."""

    state: int
    message: str | None
    data: DataT


def parse_result(
    match: Match | MatchReport, _parse: bool = True
) -> tuple[int, int] | None:
    """Parse the result string into a tuple of integers."""
    result = match.result
    home = match.homeTeamName.strip()
    guest = match.guestTeamName.strip()
    if not result:
        return None
    if result == "Abse.":
        return None
    if result == "n.an.":
        if home[0] == "(" and home[-1] == ")":
            return 0, 2
        if guest[0] == "(" and guest[-1] == ")":
            return 2, 0
        raise ValueError(f"Invalid n.an. result string for {home} vs {guest}: {result}")
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
        raise ValueError(
            f"Invalid result string for {home} vs {guest}: {result}"
        ) from e


class BFV(Consumer):
    """A Python Client for the BFV API."""

    @get("/api/service/widget/v1/team/{teamPermanentId}/matches")
    def getTeamMatches(self, teamPermanentId: str) -> Response[Matches | None]:
        """Retrieves the team's matches."""
        pass

    @get("/api/service/widget/v1/team/{teamPermanentId}/squad")
    def getTeamSquad(self, teamPermanentId: str) -> Response[Squad]:
        """Retrieves the team's squad."""
        pass

    @get("/rest/competitioncontroller/competition/id/{compoundId}")
    def getCompetition(self, compoundId: str) -> Response[Competition]:
        """Retrieves the competition."""
        pass

    @get("/rest/competitioncontroller/competition/id/{compoundId}/matchday/{matchDay}")
    def getCompetitionForMatchDay(
        self, compoundId: str, matchDay: int
    ) -> Response[Competition]:
        """Retrieves the competition."""
        pass

    @get("/api/service/widget/v1/competition/{compoundId}/topscorer")
    def getCompetitionTopScorer(self, compoundId: str) -> Response[TopScorer | None]:
        """Retrieves the competition's top scorer."""

    @get("/rest/competitioncontroller/competition/table/{tableType}/id/{compoundId}")
    def getCompetitionStandings(
        self,
        compoundId: str,
        tableType: Literal[
            "", "home", "away", "firsthalfseason", "secondhalfseason"
        ] = "",
    ) -> Response[Standings]:
        """Retrieves the competition's standings."""
        pass

    @get("/rest/clubcontroller/fixtures/id/{clubId}/matchtype/{matchType}")
    def getClubMatches(
        self, clubId: str, matchType: Literal["all", "home", "away"] = "all"
    ) -> Response[ShortMatches]:
        """Retrieves the club's matches."""
        pass

    @get("/api/service/widget/v1/club/{clubId}/info")
    def getClubInfo(self, clubId: str) -> Response[ClubInfo]:
        """Retrieves the club's information."""
        pass

    @get("/api/service/widget/v1/club/info?teamPermanentId={teamPermanentId}")
    def getClubInfoFromTeam(self, teamPermanentId: str) -> Response[ClubInfo]:
        """Retrieves the team's information."""
        pass

    @get("/rest/matchcontroller/matchreport/id/{matchId}")
    def getMatchReport(self, matchId: str) -> Response[MatchReport]:
        """Retrieves the match report."""
        pass


bfv = BFV(base_url="https://widget-prod.bfv.de")


def test_all() -> None:
    fcbayern_u13 = "01BKG17M3S000000VV0AG811VTNTKEKF"

    result = bfv.getClubInfoFromTeam(fcbayern_u13).data
    club_id = result.club.id

    matches = bfv.getClubMatches(club_id).data.matches
    unique_competitions = set(match.compoundId for match in matches)
    for comp in unique_competitions:
        comp_data = bfv.getCompetition(comp).data
        standings = bfv.getCompetitionStandings(comp).data
        top_scorer = bfv.getCompetitionTopScorer(comp).data
    for match in matches:
        report = bfv.getMatchReport(match.matchId)
    print(comp_data, standings, top_scorer, report)


# test_all()
# %%
