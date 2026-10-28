import pytest

from api.stay import day_bounds, pair_sessions


def closed(entrada, saida, seconds):
    return {"entrada": entrada, "saida": saida, "duration_seconds": seconds, "sem_saida": False}


def open_(entrada):
    return {"entrada": entrada, "saida": None, "duration_seconds": None, "sem_saida": True}


def test_closed_session_has_duration_in_seconds():
    events = [("entrada", "2026-10-28T12:00:00Z"), ("saida", "2026-10-28T13:30:00Z")]
    assert pair_sessions(events) == [closed("2026-10-28T12:00:00Z", "2026-10-28T13:30:00Z", 5400)]


def test_multiple_sessions_keep_entry_order():
    events = [
        ("entrada", "2026-10-28T11:00:00Z"),
        ("saida", "2026-10-28T12:00:00Z"),
        ("entrada", "2026-10-28T15:00:00Z"),
        ("saida", "2026-10-28T15:10:00Z"),
    ]
    assert pair_sessions(events) == [
        closed("2026-10-28T11:00:00Z", "2026-10-28T12:00:00Z", 3600),
        closed("2026-10-28T15:00:00Z", "2026-10-28T15:10:00Z", 600),
    ]


def test_open_session_is_kept_and_flagged():
    events = [("entrada", "2026-10-28T11:00:00Z"), ("saida", "2026-10-28T12:00:00Z"), ("entrada", "2026-10-28T20:00:00Z")]
    assert pair_sessions(events)[1] == open_("2026-10-28T20:00:00Z")


def test_double_entry_flags_first_and_opens_second():
    events = [("entrada", "2026-10-28T11:00:00Z"), ("entrada", "2026-10-28T12:00:00Z"), ("saida", "2026-10-28T12:30:00Z")]
    assert pair_sessions(events) == [
        open_("2026-10-28T11:00:00Z"),
        closed("2026-10-28T12:00:00Z", "2026-10-28T12:30:00Z", 1800),
    ]


def test_orphan_exit_is_ignored():
    events = [
        ("saida", "2026-10-28T10:00:00Z"),
        ("entrada", "2026-10-28T11:00:00Z"),
        ("saida", "2026-10-28T12:00:00Z"),
        ("saida", "2026-10-28T13:00:00Z"),
    ]
    assert pair_sessions(events) == [closed("2026-10-28T11:00:00Z", "2026-10-28T12:00:00Z", 3600)]


def test_day_boundary_is_sao_paulo_midnight():
    assert day_bounds("2026-10-28") == ("2026-10-28T03:00:00Z", "2026-10-29T03:00:00Z")


@pytest.mark.parametrize("value", ["", "2026-13-01", "2026-02-30", "28/10/2026", "2026-1-5", "20261028"])
def test_day_boundary_rejects_invalid_date(value):
    with pytest.raises(ValueError):
        day_bounds(value)
