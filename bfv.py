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

    @get("/api/service/widget/v1/team/{team_id}/matches")
    def get_team_matches(self, team_id: str) -> Response[Matches | None]:
        """Retrieves the team's matches."""

    @get("/api/service/widget/v1/team/{team_id}/squad")
    def get_team_squad(self, team_id: str) -> Response[Squad]:
        """Retrieves the team's squad."""

    @get("/rest/competitioncontroller/competition/id/{competition_id}")
    def get_competition(self, competition_id: str) -> Response[Competition]:
        """Retrieves the competition for the current match day."""

    @get(
        "/rest/competitioncontroller/competition/id/{competition_id}/matchday/{match_day}"
    )
    def get_competition_for_match_day(
        self, competition_id: str, match_day: int
    ) -> Response[Competition]:
        """Retrieves the competition for the given match day."""

    @get("/api/service/widget/v1/competition/{competition_id}/topscorer")
    def get_competition_top_scorer(
        self, competition_id: str
    ) -> Response[TopScorer | None]:
        """Retrieves the competition's top scorer."""

    @get(
        "/rest/competitioncontroller/competition/table/{standings_type}/id/{competition_id}"
    )
    def get_competition_standings(
        self,
        competition_id: str,
        standings_type: Literal[
            "", "home", "away", "firsthalfseason", "secondhalfseason"
        ] = "",
    ) -> Response[Standings]:
        """Retrieves the competition's standings."""

    @get("/rest/clubcontroller/fixtures/id/{club_id}/matchtype/{match_type}")
    def get_club_matches(
        self, club_id: str, match_type: Literal["all", "home", "away"] = "all"
    ) -> Response[ShortMatches]:
        """Retrieves the club's matches."""

    @get("/api/service/widget/v1/club/{club_id}/info")
    def get_club_info(self, club_id: str) -> Response[ClubInfo]:
        """Retrieves the club's information."""

    @get("/api/service/widget/v1/club/info?teamPermanentId={team_id}")
    def get_club_info_from_team(self, team_id: str) -> Response[ClubInfo]:
        """Retrieves the club's information from a team ID."""

    @get("/rest/matchcontroller/matchreport/id/{match_id}")
    def get_match_report(self, match_id: str) -> Response[MatchReport]:
        """Retrieves the match report."""


bfv = BFV(base_url="https://widget-prod.bfv.de")


def test_all() -> None:
    fcbayern_u13 = "01BKG17M3S000000VV0AG811VTNTKEKF"

    result = bfv.get_club_info_from_team(fcbayern_u13).data
    club_id = result.club.id

    matches = bfv.get_club_matches(club_id).data.matches
    unique_competitions = set(match.compoundId for match in matches)
    for comp in unique_competitions:
        comp_data = bfv.get_competition(comp).data
        standings = bfv.get_competition_standings(comp).data
        top_scorer = bfv.get_competition_top_scorer(comp).data
    for match in matches:
        report = bfv.get_match_report(match.matchId)
    print(comp_data, standings, top_scorer, report)
