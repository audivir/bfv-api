"""Tests for bfv_api.ineligibility."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bfv_api import ineligibility
from bfv_api.bfv import BFV, CompetitionLevel, EventType
from bfv_api.ineligibility import (
    KA_PLAYER,
    Ineligibility,
    PlayerStatus,
    TeamSort,
    ViolatingMatch,
    check_for_ineligibility,
    find_teams,
    get_matches_with_players,
    get_team_info,
    main,
    missing_value,
)
from tests.conftest import (
    make_match,
    make_match_event,
    make_match_player,
    make_match_report,
    make_match_team_info,
    make_players_match,
)


def test_missing_value_raises() -> None:
    with pytest.raises(ValueError, match="Missing value for home team ID"):
        missing_value("home team ID")


def test_team_sort_lt_not_implemented() -> None:
    team = TeamSort(level=CompetitionLevel.kreisliga, name="Team I")
    assert team.__lt__(42) is NotImplemented


def test_team_sort_lt_equal() -> None:
    team_a = TeamSort(level=CompetitionLevel.kreisliga, name="Team I")
    team_b = TeamSort(level=CompetitionLevel.kreisliga, name="Team I")
    assert (team_a < team_b) is False


def test_team_sort_lt_different_level() -> None:
    lower = TeamSort(level=CompetitionLevel.a_klasse, name="Team")
    higher = TeamSort(level=CompetitionLevel.kreisliga, name="Team")
    assert (lower < higher) is True


def test_team_sort_lt_roman_numeral_and_cleanup_tokens() -> None:
    team_two = TeamSort(level=CompetitionLevel.kreisliga, name="FC Foo II")
    team_three = TeamSort(level=CompetitionLevel.kreisliga, name="FC Foo III (zg.)")
    # team III is ranked lower than team II.
    assert (team_three < team_two) is True
    assert (team_two < team_three) is False


def test_team_sort_lt_same_roman_numeral_raises() -> None:
    team_a = TeamSort(level=CompetitionLevel.kreisliga, name="FC Foo")
    team_b = TeamSort(level=CompetitionLevel.kreisliga, name="FC Bar")
    with pytest.raises(ValueError, match="Same roman numeral"):
        _ = team_a < team_b


def test_get_team_info_missing_report_info() -> None:
    report = make_match_report(has_report_info=False)
    with pytest.raises(ValueError, match="No match report info"):
        get_team_info(report, "C1")


def test_get_team_info_home() -> None:
    home_info = make_match_team_info()
    report = make_match_report(home_club_id="C1", guest_club_id="C2", home_info=home_info)
    assert get_team_info(report, "C1") is home_info


def test_get_team_info_home_missing() -> None:
    report = make_match_report(home_club_id="C1", guest_club_id="C2", home_info=None)
    with pytest.raises(ValueError, match="No information about home team"):
        get_team_info(report, "C1")


def test_get_team_info_guest() -> None:
    guest_info = make_match_team_info()
    report = make_match_report(home_club_id="C1", guest_club_id="C2", guest_info=guest_info)
    assert get_team_info(report, "C2") is guest_info


def test_get_team_info_guest_missing() -> None:
    report = make_match_report(home_club_id="C1", guest_club_id="C2", guest_info=None)
    with pytest.raises(ValueError, match="No information about guest team"):
        get_team_info(report, "C2")


def test_get_team_info_unknown_club() -> None:
    report = make_match_report(home_club_id="C1", guest_club_id="C2")
    with pytest.raises(ValueError, match="Could not find team by id"):
        get_team_info(report, "C3")


class _FakeShortMatchesData:
    def __init__(self, matches: list[object]) -> None:
        self.matches = matches


class _FakeResponse:
    def __init__(self, data: object) -> None:
        self.data = data


class _FakeClub:
    id = "CLUB1"


class _FakeClubInfoData:
    club = _FakeClub()


def test_get_matches_with_players_no_kickoff_time_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = make_match(kickoff_time=None)
    monkeypatch.setattr(
        BFV,
        "get_team_matches",
        lambda _: _FakeResponse(_FakeShortMatchesData([match])),
    )
    monkeypatch.setattr(
        BFV,
        "get_club_info_from_team",
        lambda _: _FakeResponse(_FakeClubInfoData()),
    )

    with pytest.raises(ValueError, match="No kickoff time provided"):
        get_matches_with_players("T1", 1)


def test_get_matches_with_players_skips_non_meisterschaften(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = make_match(competition_type="Pokale")
    monkeypatch.setattr(
        BFV,
        "get_team_matches",
        lambda _: _FakeResponse(_FakeShortMatchesData([match])),
    )
    monkeypatch.setattr(
        BFV,
        "get_club_info_from_team",
        lambda _: _FakeResponse(_FakeClubInfoData()),
    )

    assert get_matches_with_players("T1", 1) == []


def test_get_matches_with_players_success(monkeypatch: pytest.MonkeyPatch) -> None:
    match = make_match()
    starter = make_match_player(name="Starter", substitute=False, photo_id="1")
    sub = make_match_player(name="Sub", substitute=True, photo_id="2")
    sub_event = make_match_event(event_type=EventType.SUBSTITUTE_IN, minute=60, player=sub)
    home_info = make_match_team_info(players=[starter, sub], events=[sub_event])
    report = make_match_report(home_club_id="CLUB1", guest_club_id="OTHER", home_info=home_info)

    monkeypatch.setattr(
        BFV,
        "get_team_matches",
        lambda _: _FakeResponse(_FakeShortMatchesData([match])),
    )
    monkeypatch.setattr(
        BFV,
        "get_club_info_from_team",
        lambda _: _FakeResponse(_FakeClubInfoData()),
    )
    monkeypatch.setattr(BFV, "get_match_report", lambda _: _FakeResponse(report))

    [players_match] = get_matches_with_players("T1", 1)
    assert players_match.players[("Starter", "1")] == (False, None)
    assert players_match.players[("Sub", "2")] == (True, 60)


def test_get_matches_with_players_earlier_substitute_minute_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = make_match()
    sub = make_match_player(name="Sub", substitute=True, photo_id="2")
    first_sub_in = make_match_event(event_type=EventType.SUBSTITUTE_IN, minute=70, player=sub)
    second_sub_in = make_match_event(event_type=EventType.SUBSTITUTE_IN, minute=50, player=sub)
    ignored_event = make_match_event(event_type=EventType.GOAL, minute=10, player=None)
    home_info = make_match_team_info(
        players=[sub], events=[ignored_event, first_sub_in, second_sub_in]
    )
    report = make_match_report(home_club_id="CLUB1", guest_club_id="OTHER", home_info=home_info)

    monkeypatch.setattr(
        BFV,
        "get_team_matches",
        lambda _: _FakeResponse(_FakeShortMatchesData([match])),
    )
    monkeypatch.setattr(
        BFV,
        "get_club_info_from_team",
        lambda _: _FakeResponse(_FakeClubInfoData()),
    )
    monkeypatch.setattr(BFV, "get_match_report", lambda _: _FakeResponse(report))

    [players_match] = get_matches_with_players("T1", 1)
    assert players_match.players[("Sub", "2")] == (True, 50)


def test_get_matches_with_players_substitute_without_player_skips_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = make_match()
    event = make_match_event(event_type=EventType.SUBSTITUTE_IN, minute=60, player=None)
    home_info = make_match_team_info(players=[], events=[event])
    report = make_match_report(home_club_id="CLUB1", guest_club_id="OTHER", home_info=home_info)

    calls: list[str] = []
    monkeypatch.setattr(
        BFV,
        "get_team_matches",
        lambda _: _FakeResponse(_FakeShortMatchesData([match])),
    )
    monkeypatch.setattr(
        BFV,
        "get_club_info_from_team",
        lambda _: _FakeResponse(_FakeClubInfoData()),
    )
    monkeypatch.setattr(BFV, "get_match_report", lambda _: _FakeResponse(report))

    assert get_matches_with_players("T1", 1, calls.append) == []
    assert calls


def test_get_matches_with_players_substitute_not_in_lineup_skips_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = make_match()
    unlisted = make_match_player(name="Ghost", substitute=True, photo_id="9")
    event = make_match_event(event_type=EventType.SUBSTITUTE_IN, minute=60, player=unlisted)
    home_info = make_match_team_info(players=[], events=[event])
    report = make_match_report(home_club_id="CLUB1", guest_club_id="OTHER", home_info=home_info)

    monkeypatch.setattr(
        BFV,
        "get_team_matches",
        lambda _: _FakeResponse(_FakeShortMatchesData([match])),
    )
    monkeypatch.setattr(
        BFV,
        "get_club_info_from_team",
        lambda _: _FakeResponse(_FakeClubInfoData()),
    )
    monkeypatch.setattr(BFV, "get_match_report", lambda _: _FakeResponse(report))

    assert get_matches_with_players("T1", 1) == []


def _mock_staffel(
    monkeypatch: pytest.MonkeyPatch,
    *,
    competition_type: str = "Meisterschaften",
    team_type: str = "Herren",
    level: str = "Kreisliga",
    area: str = "Nordbayern",
) -> None:
    class _FakeTeam:
        compoundId = "COMP1"  # noqa: N815

    class _FakeMatchesData:
        team = _FakeTeam()

    class _FakeCompetition:
        staffelzusatz = f"{competition_type} | {team_type} | {level} | {area}"

    monkeypatch.setattr(BFV, "get_team_matches", lambda _: _FakeResponse(_FakeMatchesData()))
    monkeypatch.setattr(BFV, "get_competition", lambda _: _FakeResponse(_FakeCompetition()))


def test_check_for_ineligibility_no_extra_teams() -> None:
    assert check_for_ineligibility("T1") == Ineligibility(0, 0, [])


def test_check_for_ineligibility_wrong_competition_type(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_staffel(monkeypatch, competition_type="Pokale")
    with pytest.raises(ValueError, match="Currently only Herren Meisterschaften supported"):
        check_for_ineligibility("T1", "T2")


def test_check_for_ineligibility_level_too_high(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_staffel(monkeypatch, level="Bundesliga")
    with pytest.raises(ValueError, match="Currently supports only clubs at or below Bayernliga"):
        check_for_ineligibility("T1", "T2")


def test_check_for_ineligibility_full_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_staffel(monkeypatch, level="Kreisliga")

    p1 = ("P1", "1")
    p2 = KA_PLAYER

    t1_matches = [
        make_players_match(
            team=1, kickoff=datetime(2025, 12, 20, tzinfo=timezone.utc), players={p1: (False, None)}
        ),
        make_players_match(
            team=1,
            kickoff=datetime(2026, 1, 10, tzinfo=timezone.utc),
            players={p1: (False, None), p2: (True, 60)},
        ),
    ]
    t2_matches = [
        make_players_match(
            team=2,
            kickoff=datetime(2026, 1, 12, tzinfo=timezone.utc),
            players={p1: (False, None), p2: (True, 60)},
        ),
        make_players_match(team=2, kickoff=datetime(2026, 1, 13, tzinfo=timezone.utc), players={}),
        make_players_match(team=2, kickoff=datetime(2026, 1, 14, tzinfo=timezone.utc), players={}),
        make_players_match(
            team=2, kickoff=datetime(2026, 1, 15, tzinfo=timezone.utc), players={p1: (False, None)}
        ),
    ]
    matches_by_team = {"T1": t1_matches, "T2": t2_matches}

    monkeypatch.setattr(
        ineligibility,
        "get_matches_with_players",
        lambda tid, unused_ix, unused_sp_print=None: matches_by_team[tid],
    )

    result = check_for_ineligibility("T1", "T2")

    assert result.n_teams == 2
    assert result.allowed_violations == 1

    m3, m4, m5, m6 = result.matches[-4:]
    # first T2 match: P1 is banned (first-half use within 15 days, no sat-out yet), and the
    # KA_PLAYER is flagged as a second-half violation.
    assert p1 in m3.first_half
    assert p2 in m3.second_half
    assert m3.ka_player_sec is True
    # P1 sits out T2's next two matches, building up sat_out_games.
    assert m4.first_half == {}
    assert m5.first_half == {}
    # by the fourth T2 match, P1's sat-out count reached the quota and is no longer banned.
    assert p1 not in m6.first_half


def test_check_for_ineligibility_winter_break_reference_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_staffel(monkeypatch, level="Kreisliga")

    p1 = ("P1", "1")
    p_early = ("PE", "5")

    t1_matches = [
        make_players_match(
            team=1,
            kickoff=datetime(2025, 12, 1, tzinfo=timezone.utc),
            players={p_early: (False, None)},
        ),
        make_players_match(
            team=1, kickoff=datetime(2025, 12, 20, tzinfo=timezone.utc), players={p1: (False, None)}
        ),
        make_players_match(team=1, kickoff=datetime(2026, 1, 10, tzinfo=timezone.utc), players={}),
    ]
    t2_matches = [
        make_players_match(
            team=2, kickoff=datetime(2026, 1, 12, tzinfo=timezone.utc), players={p1: (False, None)}
        ),
    ]
    matches_by_team = {"T1": t1_matches, "T2": t2_matches}

    monkeypatch.setattr(
        ineligibility,
        "get_matches_with_players",
        lambda tid, unused_ix, unused_sp_print=None: matches_by_team[tid],
    )

    result = check_for_ineligibility("T1", "T2")

    t2_check = result.matches[-1]
    assert p1 in t2_check.first_half


def test_check_for_ineligibility_stale_second_half_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_staffel(monkeypatch, level="Kreisliga")

    p_old = ("POld", "6")

    t1_matches = [
        make_players_match(
            team=1, kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc), players={p_old: (True, 60)}
        ),
    ]
    t2_matches = [
        make_players_match(
            team=2,
            kickoff=datetime(2026, 2, 1, tzinfo=timezone.utc),
            players={p_old: (False, None)},
        ),
    ]
    matches_by_team = {"T1": t1_matches, "T2": t2_matches}

    monkeypatch.setattr(
        ineligibility,
        "get_matches_with_players",
        lambda tid, unused_ix, unused_sp_print=None: matches_by_team[tid],
    )

    result = check_for_ineligibility("T1", "T2")

    t2_check = result.matches[-1]
    assert p_old not in t2_check.first_half
    assert p_old not in t2_check.second_half


def test_check_for_ineligibility_ka_player_first_and_plain_second_half(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_staffel(monkeypatch, level="Kreisliga")

    p_other = ("POther", "7")

    t1_matches = [
        make_players_match(
            team=1,
            kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
            players={KA_PLAYER: (False, None), p_other: (True, 60)},
        ),
    ]
    t2_matches = [
        make_players_match(
            team=2,
            kickoff=datetime(2026, 1, 5, tzinfo=timezone.utc),
            players={KA_PLAYER: (False, None), p_other: (False, None)},
        ),
    ]
    matches_by_team = {"T1": t1_matches, "T2": t2_matches}

    monkeypatch.setattr(
        ineligibility,
        "get_matches_with_players",
        lambda tid, unused_ix, unused_sp_print=None: matches_by_team[tid],
    )

    result = check_for_ineligibility("T1", "T2")

    t2_check = result.matches[-1]
    assert KA_PLAYER in t2_check.first_half
    assert t2_check.ka_player_first is True
    assert p_other in t2_check.second_half
    assert t2_check.ka_player_sec is False


class _FakeClubData:
    def __init__(self, name: str) -> None:
        self.club = type("_C", (), {"name": name})()


def _mock_club(
    monkeypatch: pytest.MonkeyPatch, *, club_name: str = "My Club", matches: list[object]
) -> None:
    monkeypatch.setattr(BFV, "get_club_info", lambda _: _FakeResponse(_FakeClubData(club_name)))
    monkeypatch.setattr(
        BFV,
        "get_club_matches",
        lambda unused_cid, match_type=None: _FakeResponse(  # noqa: ARG005
            _FakeShortMatchesData(matches)
        ),
    )


def _mock_competition_for(monkeypatch: pytest.MonkeyPatch, levels: dict[str, str]) -> None:
    class _FakeCompetition:
        def __init__(self, level: str) -> None:
            self.staffelzusatz = f"Meisterschaften | Herren | {level} | Nordbayern"

    monkeypatch.setattr(
        BFV,
        "get_competition",
        lambda compound_id: _FakeResponse(_FakeCompetition(levels[compound_id])),
    )


def test_find_teams_no_matching_teams(monkeypatch: pytest.MonkeyPatch) -> None:
    wrong_team_type = make_match(team_type="Frauen")
    wrong_competition = make_match(competition_type="Pokale")
    no_pattern_match = make_match(home_team_name="Foo", guest_team_name="Bar")

    _mock_club(
        monkeypatch,
        club_name="Zzz Unrelated",
        matches=[wrong_team_type, wrong_competition, no_pattern_match],
    )

    club_name, found_teams = find_teams("C1", None)

    assert club_name == "Zzz Unrelated"
    assert found_teams is None


def test_find_teams_missing_permanent_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    match = make_match(home_team_name="My Club", home_team_permanent_id=None)
    _mock_club(monkeypatch, club_name="My Club", matches=[match])

    with pytest.raises(ValueError, match="Team ID missing"):
        find_teams("C1", None)


def test_find_teams_success(monkeypatch: pytest.MonkeyPatch) -> None:
    match = make_match(home_team_name="My Club", guest_team_name="Other")
    _mock_club(monkeypatch, club_name="My Club", matches=[match])
    _mock_competition_for(monkeypatch, {"C1": "Kreisliga"})

    club_name, found_teams = find_teams("C1", "My Club")

    assert club_name == "My Club"
    assert found_teams is not None
    assert found_teams[0].name == "My Club"
    assert found_teams[0].level == CompetitionLevel.kreisliga


def test_get_matches_with_players_missing_home_team_id(monkeypatch: pytest.MonkeyPatch) -> None:
    match = make_match(home_team_permanent_id=None)
    home_info = make_match_team_info()
    report = make_match_report(home_club_id="CLUB1", guest_club_id="OTHER", home_info=home_info)

    monkeypatch.setattr(
        BFV,
        "get_team_matches",
        lambda _: _FakeResponse(_FakeShortMatchesData([match])),
    )
    monkeypatch.setattr(
        BFV,
        "get_club_info_from_team",
        lambda _: _FakeResponse(_FakeClubInfoData()),
    )
    monkeypatch.setattr(BFV, "get_match_report", lambda _: _FakeResponse(report))

    assert get_matches_with_players("T1", 1) == []


class _FakeFoundTeam:
    def __init__(self, *, team_id: str, name: str, level: CompetitionLevel) -> None:
        self.id = team_id
        self.name = name
        self.level = level


def test_main_no_teams_found_without_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ineligibility, "find_teams", lambda unused_cid, unused_pattern: ("Club", None)
    )

    with pytest.raises(SystemExit):
        main("C1")


def test_main_no_teams_found_with_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ineligibility, "find_teams", lambda unused_cid, unused_pattern: ("Club", None)
    )

    with pytest.raises(SystemExit):
        main("C1", pattern="xyz")


def test_main_single_team(monkeypatch: pytest.MonkeyPatch) -> None:
    team = _FakeFoundTeam(team_id="T1", name="Team I", level=CompetitionLevel.kreisliga)
    monkeypatch.setattr(
        ineligibility, "find_teams", lambda unused_cid, unused_pattern: ("Club", [team])
    )
    monkeypatch.setattr(
        ineligibility, "check_for_ineligibility", lambda *unused_ids: Ineligibility(1, 1, [])
    )

    main("C1")


def test_main_reports_all_violation_states(monkeypatch: pytest.MonkeyPatch) -> None:
    team1 = _FakeFoundTeam(team_id="T1", name="Team I", level=CompetitionLevel.bezirksliga)
    team2 = _FakeFoundTeam(team_id="T2", name="Team II", level=CompetitionLevel.kreisliga)
    monkeypatch.setattr(
        ineligibility, "find_teams", lambda unused_cid, unused_pattern: ("Club", [team1, team2])
    )

    status = PlayerStatus(
        higher_team=1, match_date=datetime(2026, 1, 1, tzinfo=timezone.utc).date(), first_half=True
    )
    status_winter = PlayerStatus(
        higher_team=1,
        match_date=datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
        first_half=True,
        is_pre_winter=True,
    )
    sec_status = PlayerStatus(
        higher_team=1, match_date=datetime(2026, 1, 1, tzinfo=timezone.utc).date(), first_half=False
    )

    clean_match = ViolatingMatch(
        team=2,
        date=datetime(2026, 1, 5, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest",
        ka_player_first=False,
        ka_player_sec=False,
        first_half={},
        second_half={},
    )
    illegal_overhead2 = ViolatingMatch(
        team=2,
        date=datetime(2026, 1, 6, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest",
        ka_player_first=False,
        ka_player_sec=False,
        first_half={
            ("P1", "1"): (status, 3),
            ("P2", "2"): (status_winter, 3),
            ("P5", "5"): (status, 3),
        },
        second_half={},
    )
    prob_legal = ViolatingMatch(
        team=2,
        date=datetime(2026, 1, 7, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest",
        ka_player_first=True,
        ka_player_sec=False,
        first_half={KA_PLAYER: (status, 3), ("P6", "6"): (status, 3)},
        second_half={},
    )
    illegal_overhead1_no_ka = ViolatingMatch(
        team=2,
        date=datetime(2026, 1, 8, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest",
        ka_player_first=False,
        ka_player_sec=False,
        first_half={("P3", "3"): (status, 3), ("P7", "7"): (status, 3)},
        second_half={},
    )
    legal = ViolatingMatch(
        team=2,
        date=datetime(2026, 1, 9, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest",
        ka_player_first=False,
        ka_player_sec=False,
        first_half={("P4", "4"): (status, 3)},
        second_half={},
    )
    over_limit_with_ka_sec = ViolatingMatch(
        team=2,
        date=datetime(2026, 1, 10, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest",
        ka_player_first=False,
        ka_player_sec=True,
        first_half={},
        second_half={(f"S{i}", str(i)): (sec_status, 3) for i in range(6)},
    )

    ineligibility_result = Ineligibility(
        n_teams=2,
        allowed_violations=1,
        matches=[
            clean_match,
            illegal_overhead2,
            prob_legal,
            illegal_overhead1_no_ka,
            legal,
            over_limit_with_ka_sec,
        ],
    )
    monkeypatch.setattr(
        ineligibility, "check_for_ineligibility", lambda *unused_ids: ineligibility_result
    )

    main("C1")
