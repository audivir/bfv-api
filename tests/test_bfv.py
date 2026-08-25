"""Tests for bfv_api.bfv."""

from __future__ import annotations

from bfv_api.bfv import BFV


def test_all() -> None:
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
            print(comp_data, standings, top_scorer)
    for ix, match in enumerate(matches):
        report = BFV.get_match_report(match.matchId)
        if ix == 0:
            print(report)
