# %%
from bfv import bfv, Match as BFVMatch
from table import Match, show_table

tsv_kornburg = "016PE7FISS000000VV0AG811VTE5EA5R"

# get the competition id
comp = bfv.getTeamMatches(tsv_kornburg).data.team.compoundId

# get the current match day
current_match_day = bfv.getCompetition(comp).data.actualMatchDay

# get all matches played so far
all_matches: list[BFVMatch] = []
for match_day in range(1, int(current_match_day) + 1):
    matches = bfv.getCompetitionForMatchDay(comp, match_day).data.matches
    all_matches.extend(matches)

# take only the matches that have a valid result
simple_matches: list[Match] = []
for bfv_match in all_matches:
    if not bfv_match.parsed_result:
        continue
    match = Match(
        bfv_match.homeTeamName, bfv_match.guestTeamName, *bfv_match.parsed_result, 0, 0
    )
    simple_matches.append(match)

# remove duplicates
# (matches that have been deferred from a previous match day are listed twice)
simple_matches = list(set(simple_matches))

# Show the table with default sorting
show_table(simple_matches)
