"""Example of how to use the bfv_api to get the standings of a team."""

from __future__ import annotations

from bfv_api import BFV, BFVMatch, Match, show_standings

tsv_kornburg = "016PE7FISS000000VV0AG811VTE5EA5R"

# get the competition id
comp = BFV.get_team_matches(tsv_kornburg).data.team.compoundId

# get the current match day
current_match_day = BFV.get_competition(comp).data.actualMatchDay

# get all matches played so far
all_matches: list[BFVMatch] = []
for match_day in range(1, int(current_match_day) + 1):
    matches = BFV.get_competition_for_match_day(comp, match_day).data.matches
    all_matches.extend(matches)

# take only the matches that have a valid result
simple_matches: list[Match] = []
for bfv_match in all_matches:
    if not bfv_match.parsed_result:
        continue
    match = Match(bfv_match.homeTeamName, bfv_match.guestTeamName, *bfv_match.parsed_result, 0, 0)
    simple_matches.append(match)

# remove duplicates
# (matches that have been deferred from a previous match day are listed twice)
simple_matches = list(set(simple_matches))

# Show standings with default sorting
show_standings(simple_matches)
