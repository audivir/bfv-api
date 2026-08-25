"""Tests for bfv_api.new_ineligibility."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bfv_api import new_ineligibility
from bfv_api.bfv import BFV, CompetitionLevel, StaffelInfo
from bfv_api.new_ineligibility import (
    AppearanceKind,
    CheckedMatch,
    HigherTeamAppearance,
    appearances_in_window,
    check_for_ineligibility,
    check_match,
    classify_appearance,
    is_a_klasse_lowest_tier,
    is_b_c_klasse,
    is_kreisebene,
    is_second_half_bonus_eligible,
    main,
    used_players,
)
from tests.conftest import make_players_match


def test_is_a_klasse_lowest_tier_default_false() -> None:
    assert is_a_klasse_lowest_tier("Nordbayern") is False


def test_is_a_klasse_lowest_tier_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        new_ineligibility, "KREISE_WHERE_A_KLASSE_IS_LOWEST", frozenset({"Nordbayern"})
    )
    assert is_a_klasse_lowest_tier("Kreis Nordbayern Ost") is True


def test_is_kreisebene_true() -> None:
    assert is_kreisebene(CompetitionLevel.kreisklasse) is True


def test_is_kreisebene_false() -> None:
    assert is_kreisebene(CompetitionLevel.bezirksliga) is False


def test_is_b_c_klasse_true() -> None:
    assert is_b_c_klasse(CompetitionLevel.b_klasse) is True


def test_is_b_c_klasse_false() -> None:
    assert is_b_c_klasse(CompetitionLevel.a_klasse) is False


def test_second_half_bonus_eligible_via_b_c_klasse() -> None:
    assert is_second_half_bonus_eligible(CompetitionLevel.b_klasse, "Nordbayern") is True


def test_second_half_bonus_eligible_via_lowest_a_klasse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        new_ineligibility, "KREISE_WHERE_A_KLASSE_IS_LOWEST", frozenset({"Nordbayern"})
    )
    assert is_second_half_bonus_eligible(CompetitionLevel.a_klasse, "Nordbayern") is True


def test_second_half_bonus_eligible_a_klasse_not_lowest() -> None:
    assert is_second_half_bonus_eligible(CompetitionLevel.a_klasse, "Nordbayern") is False


def test_second_half_bonus_eligible_false() -> None:
    assert is_second_half_bonus_eligible(CompetitionLevel.kreisliga, "Nordbayern") is False


def test_classify_appearance_second_half_only() -> None:
    assert classify_appearance(True, 60) is AppearanceKind.SECOND_HALF_ONLY


def test_classify_appearance_full_starter() -> None:
    assert classify_appearance(False, None) is AppearanceKind.FULL


def test_classify_appearance_full_early_substitute() -> None:
    assert classify_appearance(True, 30) is AppearanceKind.FULL


def test_classify_appearance_full_unresolved_substitute() -> None:
    assert classify_appearance(True, None) is AppearanceKind.FULL


def test_used_players_filters_unresolved_substitutes() -> None:
    players = {
        ("Starter", "1"): (False, None),
        ("BenchWarmer", "2"): (True, None),
        ("SubIn", "3"): (True, 60),
    }
    assert used_players(players) == {("Starter", "1"), ("SubIn", "3")}


def test_get_staffel_info(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeTeam:
        compoundId = "COMP1"  # noqa: N815

    class _FakeMatchesData:
        team = _FakeTeam()

    class _FakeMatchesResponse:
        data = _FakeMatchesData()

    class _FakeCompetition:
        staffelzusatz = "Meisterschaften | Herren | Kreisliga | Nordbayern"

    class _FakeCompetitionResponse:
        data = _FakeCompetition()

    monkeypatch.setattr(BFV, "get_team_matches", lambda _: _FakeMatchesResponse())
    monkeypatch.setattr(
        BFV,
        "get_competition",
        lambda compound_id: _FakeCompetitionResponse(),  # noqa: ARG005
    )

    staffel_info = new_ineligibility.get_staffel_info("T1")
    assert staffel_info.competitionLevel == CompetitionLevel.kreisliga
    assert staffel_info.competitionArea == "Nordbayern"


def test_appearances_in_window() -> None:
    higher_matches = [
        make_players_match(
            kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
            players={("A", "1"): (False, None)},
        ),
        make_players_match(
            kickoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
            players={("A", "1"): (True, 60), ("B", "2"): (False, None)},
        ),
        make_players_match(
            kickoff=datetime(2026, 1, 15, tzinfo=timezone.utc),
            players={("A", "1"): (False, None)},
        ),
        make_players_match(
            kickoff=datetime(2026, 1, 22, tzinfo=timezone.utc),
            players={("C", "3"): (False, None)},
        ),
    ]

    appearances = appearances_in_window(
        higher_matches,
        higher_team=1,
        higher_level=CompetitionLevel.kreisliga,
        window_start=datetime(2025, 12, 25, tzinfo=timezone.utc),
        window_end=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )

    # player A: FULL on 01/01, SECOND_HALF_ONLY on 01/08 (kept as FULL, no downgrade), then
    # FULL again on 01/15 (already FULL, stays FULL).
    assert appearances[("A", "1")].kind is AppearanceKind.FULL
    assert appearances[("A", "1")].kickoff == datetime(2026, 1, 1, tzinfo=timezone.utc)
    # player B: only appears as SECOND_HALF_ONLY... actually starter -> FULL.
    assert appearances[("B", "2")].kind is AppearanceKind.FULL
    # player C's match on 01/22 is outside the window (>= window_end) and never reached.
    assert ("C", "3") not in appearances


def test_appearances_in_window_upgrades_to_full() -> None:
    higher_matches = [
        make_players_match(
            kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
            players={("A", "1"): (True, 60)},
        ),
        make_players_match(
            kickoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
            players={("A", "1"): (False, None)},
        ),
    ]

    appearances = appearances_in_window(
        higher_matches,
        higher_team=1,
        higher_level=CompetitionLevel.kreisliga,
        window_start=None,
        window_end=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert appearances[("A", "1")].kind is AppearanceKind.FULL
    assert appearances[("A", "1")].kickoff == datetime(2026, 1, 8, tzinfo=timezone.utc)


def test_appearances_in_window_skips_before_start() -> None:
    higher_matches = [
        make_players_match(
            kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc), players={("A", "1"): (False, None)}
        )
    ]

    appearances = appearances_in_window(
        higher_matches,
        higher_team=1,
        higher_level=CompetitionLevel.kreisliga,
        window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert appearances == {}


def _make_appearance(
    *, kind: AppearanceKind, level: CompetitionLevel = CompetitionLevel.kreisliga
) -> HigherTeamAppearance:
    return HigherTeamAppearance(
        higher_team=1,
        higher_team_level=level,
        kind=kind,
        kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        home="Home",
        guest="Guest",
    )


def test_check_match_kreisebene_and_base_quota() -> None:
    m = make_players_match(
        kickoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
        players={
            ("Full1", "1"): (False, None),
            ("Full2", "2"): (False, None),
            ("Sec1", "3"): (False, None),
            ("Sec2", "4"): (False, None),
            ("Sec3", "5"): (False, None),
        },
    )
    at_risk = {
        ("Full1", "1"): _make_appearance(kind=AppearanceKind.FULL),
        ("Full2", "2"): _make_appearance(kind=AppearanceKind.FULL),
        ("Sec1", "3"): _make_appearance(kind=AppearanceKind.SECOND_HALF_ONLY),
        ("Sec2", "4"): _make_appearance(kind=AppearanceKind.SECOND_HALF_ONLY),
        ("Sec3", "5"): _make_appearance(kind=AppearanceKind.SECOND_HALF_ONLY),
    }

    result = check_match(m, at_risk, CompetitionLevel.kreisliga, "Nordbayern")

    assert isinstance(result, CheckedMatch)
    # one full-ban player is exempted via the Kreisebene arbitrary quota.
    assert len(result.exempt) == 1 + 2  # 1 arbitrary + base second-half quota of 2
    assert len(result.violations) == 1 + 1  # 1 remaining full ban + 1 excess second-half


def test_check_match_no_kreisebene_no_bonus() -> None:
    m = make_players_match(
        kickoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
        players={("Full1", "1"): (False, None)},
    )
    at_risk = {("Full1", "1"): _make_appearance(kind=AppearanceKind.FULL)}

    result = check_match(m, at_risk, CompetitionLevel.bezirksliga, "Nordbayern")

    assert result.exempt == []
    assert len(result.violations) == 1


def test_check_match_second_half_bonus() -> None:
    m = make_players_match(
        kickoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
        players={
            ("Sec1", "1"): (False, None),
            ("Sec2", "2"): (False, None),
            ("Sec3", "3"): (False, None),
            ("Sec4", "4"): (False, None),
        },
    )
    at_risk = {
        key: _make_appearance(kind=AppearanceKind.SECOND_HALF_ONLY)
        for key in [("Sec1", "1"), ("Sec2", "2"), ("Sec3", "3"), ("Sec4", "4")]
    }

    result = check_match(m, at_risk, CompetitionLevel.b_klasse, "Nordbayern")

    # base quota 2 + Kreisebene second-half bonus 2 = 4, so all 4 are exempt.
    assert len(result.exempt) == 4
    assert result.violations == []


def test_check_for_ineligibility_no_extra_teams() -> None:
    assert check_for_ineligibility("T1") == []


def test_check_for_ineligibility(monkeypatch: pytest.MonkeyPatch) -> None:
    staffel_infos = {
        "T1": StaffelInfo(
            competitionType="Meisterschaften",
            teamType="Herren",
            competitionLevel=CompetitionLevel.bezirksliga,
            competitionArea="Nordbayern",
        ),
        "T2": StaffelInfo(
            competitionType="Meisterschaften",
            teamType="Herren",
            competitionLevel=CompetitionLevel.kreisliga,
            competitionArea="Nordbayern",
        ),
    }
    matches_by_team = {
        "T1": [
            make_players_match(
                team=1,
                kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
                players={("Star", "1"): (False, None)},
            )
        ],
        "T2": [
            make_players_match(
                team=2,
                kickoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
                players={("Star", "1"): (False, None)},
            )
        ],
    }

    monkeypatch.setattr(new_ineligibility, "get_staffel_info", lambda tid: staffel_infos[tid])
    monkeypatch.setattr(
        new_ineligibility,
        "get_matches_with_players",
        lambda tid, unused_ix, unused_sp_print=None: matches_by_team[tid],
    )

    checked = check_for_ineligibility("T1", "T2")

    assert len(checked) == 1
    assert checked[0].violations[0].player_key == ("Star", "1")


def test_check_for_ineligibility_keeps_stronger_existing_appearance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staffel_infos = {
        "T1": StaffelInfo(
            competitionType="Meisterschaften",
            teamType="Herren",
            competitionLevel=CompetitionLevel.bezirksliga,
            competitionArea="Nordbayern",
        ),
        "T2": StaffelInfo(
            competitionType="Meisterschaften",
            teamType="Herren",
            competitionLevel=CompetitionLevel.kreisliga,
            competitionArea="Nordbayern",
        ),
        "T3": StaffelInfo(
            competitionType="Meisterschaften",
            teamType="Herren",
            competitionLevel=CompetitionLevel.kreisklasse,
            competitionArea="Nordbayern",
        ),
    }
    matches_by_team = {
        "T1": [
            make_players_match(
                team=1,
                kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
                players={("Star", "1"): (False, None)},
            )
        ],
        "T2": [
            make_players_match(
                team=2,
                kickoff=datetime(2026, 1, 2, tzinfo=timezone.utc),
                players={("Star", "1"): (True, 60)},
            )
        ],
        "T3": [
            make_players_match(
                team=3,
                kickoff=datetime(2026, 1, 8, tzinfo=timezone.utc),
                players={("Star", "1"): (False, None)},
            )
        ],
    }

    monkeypatch.setattr(new_ineligibility, "get_staffel_info", lambda tid: staffel_infos[tid])
    monkeypatch.setattr(
        new_ineligibility,
        "get_matches_with_players",
        lambda tid, unused_ix, unused_sp_print=None: matches_by_team[tid],
    )

    checked = check_for_ineligibility("T1", "T2", "T3")

    # T3's checked match against T1/T2: since T1's FULL appearance for "Star" is retained over
    # T2's later SECOND_HALF_ONLY appearance, the violation stays a full-ban, not a second-half one.
    t3_check = checked[-1]
    assert t3_check.violations[0].appearance.kind is AppearanceKind.FULL


def test_main_no_teams_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        new_ineligibility, "find_teams", lambda unused_club_id, unused_pattern: ("Club", None)
    )

    with pytest.raises(SystemExit):
        main("club1")

    monkeypatch.setattr(
        new_ineligibility, "find_teams", lambda unused_club_id, unused_pattern: ("Club", None)
    )
    with pytest.raises(SystemExit):
        main("club1", pattern="xyz")


def test_main_single_team(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FoundTeam:
        id = "T1"
        name = "Team I"
        level = CompetitionLevel.kreisliga

    monkeypatch.setattr(
        new_ineligibility,
        "find_teams",
        lambda unused_club_id, unused_pattern: ("Club", [_FoundTeam()]),
    )

    main("club1")


def test_main_reports_violations_and_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FoundTeam1:
        id = "T1"
        name = "Team I"
        level = CompetitionLevel.bezirksliga

    class _FoundTeam2:
        id = "T2"
        name = "Team II"
        level = CompetitionLevel.kreisliga

    monkeypatch.setattr(
        new_ineligibility,
        "find_teams",
        lambda unused_club_id, unused_pattern: ("Club", [_FoundTeam1(), _FoundTeam2()]),
    )

    violating = CheckedMatch(
        team=2,
        date=datetime(2026, 1, 8, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest",
        exempt=[("Exempt1", "9")],
        violations=[
            new_ineligibility.MatchViolation(
                ("Full1", "1"), _make_appearance(kind=AppearanceKind.FULL)
            ),
            new_ineligibility.MatchViolation(
                ("Sec1", "2"), _make_appearance(kind=AppearanceKind.SECOND_HALF_ONLY)
            ),
        ],
    )
    clean = CheckedMatch(
        team=2,
        date=datetime(2026, 1, 15, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest2",
        exempt=[],
        violations=[],
    )
    violating_no_exempt = CheckedMatch(
        team=2,
        date=datetime(2026, 1, 22, tzinfo=timezone.utc).date(),
        home="Home",
        guest="Guest3",
        exempt=[],
        violations=[
            new_ineligibility.MatchViolation(
                ("Full2", "3"), _make_appearance(kind=AppearanceKind.FULL)
            )
        ],
    )

    monkeypatch.setattr(
        new_ineligibility,
        "check_for_ineligibility",
        lambda *unused_team_ids: [violating, clean, violating_no_exempt],
    )

    main("club1")
