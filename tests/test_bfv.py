"""Tests for bfv_api.bfv."""

from __future__ import annotations

import httpx
import pytest

from bfv_api.bfv import (
    BFV,
    Competition,
    CompetitionType,
    MatchDay,
    MatchReport,
    PlayerInfo,
    StaffelInfo,
    parse_result,
)
from tests.conftest import make_match, make_venue


def test_parsed_result_not_played() -> None:
    match = make_match(result="", guest_team_name="")
    assert match.parsed_result is None


def test_parsed_result_no_result_string() -> None:
    match = make_match(result="")
    assert match.parsed_result is None


def test_parsed_result_abgesagt() -> None:
    match = make_match(result="Abse.")
    assert match.parsed_result is None


def test_parsed_result_abgebrochen() -> None:
    match = make_match(result="Abbr.")
    assert match.parsed_result == (-1, -1)


def test_parsed_result_nicht_angetreten_home() -> None:
    match = make_match(result="n.an.", home_team_name="(Home)")
    assert match.parsed_result == (0, 2)


def test_parsed_result_nicht_angetreten_guest() -> None:
    match = make_match(result="n.an.", guest_team_name="(Guest)")
    assert match.parsed_result == (2, 0)


def test_parsed_result_nicht_angetreten_invalid() -> None:
    match = make_match(result="n.an.")
    with pytest.raises(ValueError, match=r"Invalid n\.an\. result string"):
        _ = match.parsed_result


def test_parsed_result_nach_verlaengerung() -> None:
    match = make_match(result="3:2 nE")
    assert match.parsed_result == (3, 2)


def test_parsed_result_wertung() -> None:
    match = make_match(result="2:0 w")
    assert match.parsed_result == (2, 0)


def test_parsed_result_wertung_split_failure() -> None:
    match = make_match(result="9w")
    with pytest.raises(ValueError, match="Invalid result string"):
        _ = match.parsed_result


def test_parse_result_wertung_when_already_parsed() -> None:
    match = make_match(result="0:2 w")
    with pytest.raises(ValueError, match="Invalid result string"):
        parse_result(match, _parse=False)


def test_parsed_result_valid_score() -> None:
    match = make_match(result="3:1")
    assert match.parsed_result == (3, 1)


def test_parsed_result_invalid_score() -> None:
    match = make_match(result="abc")
    with pytest.raises(ValueError, match="Invalid result string"):
        _ = match.parsed_result


def test_select_team_matches_both() -> None:
    match = make_match(home_team_name="Foo", guest_team_name="Foo Bar")
    with pytest.raises(ValueError, match="matches both teams"):
        match.select_team("Foo")


def test_select_team_matches_home() -> None:
    match = make_match(home_team_name="Foo", guest_team_name="Bar")
    result = match.select_team("Foo")
    assert result is not None
    ix, this_team, other_team = result
    assert ix == 0
    assert this_team.teamName == "Foo"
    assert other_team.teamName == "Bar"


def test_select_team_matches_guest() -> None:
    match = make_match(home_team_name="Foo", guest_team_name="Bar")
    result = match.select_team("Bar")
    assert result is not None
    ix, this_team, other_team = result
    assert ix == 1
    assert this_team.teamName == "Bar"
    assert other_team.teamName == "Foo"


def test_select_team_matches_none() -> None:
    match = make_match(home_team_name="Foo", guest_team_name="Bar")
    assert match.select_team("Baz") is None


def test_player_info_id() -> None:
    player_info = PlayerInfo(
        photoUrlThumb="", photoUrlStamp="", photoUrlImage="https://example.com/12345.jpg"
    )
    assert player_info.id == "12345"


def test_match_report_parsed_result() -> None:
    report = MatchReport(
        staffelzusatz="",
        matchId="M1",
        result="1:1",
        startDate="",
        startTime="",
        leageName="",
        season="",
        homeTeamName="Home",
        guestTeamName="Guest",
        homeTeamClubId=None,
        guestTeamClubId=None,
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
        matchReportInfo=None,
        adCode="",
    )
    assert report.parsed_result == (1, 1)


def test_staffel_info_from_model() -> None:
    class FakeModel:
        staffelzusatz = "Meisterschaften | Herren | Kreisliga | Nordbayern"

    staffel_info = StaffelInfo.from_model(FakeModel())
    assert staffel_info.competitionType == "Meisterschaften"
    assert staffel_info.teamType == "Herren"
    assert staffel_info.competitionArea == "Nordbayern"


def _make_competition(staffel_typ_name: str) -> Competition:
    return Competition(
        saison="",
        compoundId="",
        staffelId="",
        staffelname="",
        staffelzusatz="",
        staffelnr="",
        staffelTypId=CompetitionType.Meisterschaften,
        staffelTypName=staffel_typ_name,  # type: ignore[arg-type]
        adCode="",
        anzAufsteiger=0,
        anzAufsteigerq=0,
        anzAbsteigerq=0,
        anzAbsteiger=0,
        stLiveticker=False,
        matches=[],
        tabelle=None,
        spieltage=[MatchDay(spieltag="1", bezeichnung="1. Spieltag")],
        selSpieltag="1",
        actualMatchDay="1",
    )


def test_competition_post_init_consistent() -> None:
    competition = _make_competition("Meisterschaften")
    assert competition.staffelTypName == "Meisterschaften"


def test_competition_post_init_mismatch() -> None:
    with pytest.raises(ValueError, match="Competition mismatch"):
        _make_competition("Pokale")


def test_all() -> None:
    fcbayern_u13 = "01BKG17M3S000000VV0AG811VTNTKEKF"

    result = BFV.get_club_info_from_team(fcbayern_u13).data
    club_id = result.club.id

    # restrict to Meisterschaften: the only competition type the rest of the library
    # supports (see ineligibility.py), so this is the only data live-tested here.
    all_matches = BFV.get_club_matches(club_id).data.matches
    matches = [m for m in all_matches if m.competitionType == "Meisterschaften"]
    unique_competitions = {match.compoundId for match in matches}
    for ix, comp in enumerate(unique_competitions):
        comp_data = BFV.get_competition(comp).data
        # some top-tier leagues (e.g. federal Bundesliga groups) only publish home/away split
        # tables, not a default aggregate one, so a missing table here is not a failure.
        try:
            standings = BFV.get_competition_standings(comp).data
        except httpx.HTTPStatusError:
            standings = None
        top_scorer = BFV.get_competition_top_scorer(comp).data
        if ix == 0:
            print(comp_data, standings, top_scorer)
    for ix, match in enumerate(matches):
        report = BFV.get_match_report(match.matchId)
        if ix == 0:
            print(report)
