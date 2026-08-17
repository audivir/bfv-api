"""Example of retrieving team standings using bfv_api."""

from __future__ import annotations

from bfv_api import BFV, BFVMatch, Match, show_standings

if __name__ == "__main__":
    tsv_kornburg = "016PE7FISS000000VV0AG811VTE5EA5R"

    # retrieve competition ID.
    comp = BFV.get_team_matches(tsv_kornburg).data.team.compoundId

    # retrieve current match day.
    current_match_day = BFV.get_competition(comp).data.actualMatchDay

    # retrieve all matches played to date.
    all_matches: list[BFVMatch] = []
    for match_day in range(1, int(current_match_day) + 1):
        matches = BFV.get_competition_for_match_day(comp, match_day).data.matches
        all_matches.extend(matches)

    # Filter for matches with valid results.
    simple_matches: list[Match] = []
    for bfv_match in all_matches:
        if not bfv_match.parsed_result:
            continue
        match = Match(
            bfv_match.homeTeamName, bfv_match.guestTeamName, *bfv_match.parsed_result, 0, 0
        )
        simple_matches.append(match)

    # remove duplicate matches deferred from previous match days.
    simple_matches = list(set(simple_matches))

    # display standings using default sorting.
    show_standings(simple_matches)
