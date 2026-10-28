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


# --- GET /api/stay ---

_counter = iter(range(10_000))


def make_employee(client, tag, registration_id, name="Ana"):
    payload = {"name": name, "registration_id": registration_id, "rfid_tag": tag, "role": "dev"}
    return client.post("/api/employees", json=payload).get_json()["id"]


def send(client, kind, timestamp, tag="AA:01"):
    body = {"id": f"e{next(_counter)}", "type": kind, "rfid_tag": tag, "timestamp": timestamp, "source": "pi-1"}
    assert client.post("/api/events", json=body).status_code == 201


def stay(client, **query):
    return client.get("/api/stay", query_string=query)


def test_ignores_other_events(admin_client):
    ana = make_employee(admin_client, "AA:01", "R1")
    send(admin_client, "acesso_negado", "2026-10-28T11:00:00Z")
    send(admin_client, "tentativa_invasao", "2026-10-28T11:30:00Z")
    send(admin_client, "entrada", "2026-10-28T12:00:00Z", tag="FF:FF")  # unknown tag: employee_id null
    send(admin_client, "entrada", "2026-10-28T13:00:00Z")
    send(admin_client, "saida", "2026-10-28T14:00:00Z")
    body = stay(admin_client, date="2026-10-28").get_json()
    assert [e["employee_id"] for e in body["employees"]] == [ana]
    assert body["employees"][0]["sessions"] == [closed("2026-10-28T13:00:00Z", "2026-10-28T14:00:00Z", 3600)]


def test_same_timestamp_uses_insertion_order(admin_client):
    make_employee(admin_client, "AA:01", "R1")
    send(admin_client, "entrada", "2026-10-28T12:00:00Z")
    send(admin_client, "saida", "2026-10-28T12:00:00Z")
    session = stay(admin_client, date="2026-10-28").get_json()["employees"][0]["sessions"]
    assert session == [closed("2026-10-28T12:00:00Z", "2026-10-28T12:00:00Z", 0)]


def test_lists_employees_with_events_by_employee_id(admin_client):
    ana = make_employee(admin_client, "AA:01", "R1", name="Ana")
    bia = make_employee(admin_client, "AA:02", "R2", name="Bia")
    make_employee(admin_client, "AA:03", "R3", name="Caio")  # no events
    send(admin_client, "entrada", "2026-10-28T12:00:00Z", tag="AA:02")
    send(admin_client, "entrada", "2026-10-28T13:00:00Z", tag="AA:01")
    body = stay(admin_client, date="2026-10-28").get_json()
    assert body["date"] == "2026-10-28"
    assert [(e["employee_id"], e["name"]) for e in body["employees"]] == [(ana, "Ana"), (bia, "Bia")]
    assert stay(admin_client, date="2026-10-29").get_json()["employees"] == []


def test_employee_without_events(admin_client):
    caio = make_employee(admin_client, "AA:03", "R3", name="Caio")
    body = stay(admin_client, date="2026-10-28", employee_id=caio).get_json()
    assert body["employees"] == [{"employee_id": caio, "name": "Caio", "total_seconds": 0, "sessions": []}]


def test_employee_filter_returns_only_that_employee(admin_client):
    ana = make_employee(admin_client, "AA:01", "R1")
    make_employee(admin_client, "AA:02", "R2", name="Bia")
    send(admin_client, "entrada", "2026-10-28T12:00:00Z", tag="AA:01")
    send(admin_client, "entrada", "2026-10-28T12:00:00Z", tag="AA:02")
    employees = stay(admin_client, date="2026-10-28", employee_id=ana).get_json()["employees"]
    assert [e["employee_id"] for e in employees] == [ana]


def test_multiple_sessions_total_skips_open_session(admin_client):
    make_employee(admin_client, "AA:01", "R1")
    for kind, moment in (
        ("entrada", "2026-10-28T11:00:00Z"),
        ("saida", "2026-10-28T12:00:00Z"),
        ("entrada", "2026-10-28T15:00:00Z"),
        ("saida", "2026-10-28T15:10:00Z"),
        ("entrada", "2026-10-29T01:00:00Z"),  # 22:00 local, never closed
    ):
        send(admin_client, kind, moment)
    employee = stay(admin_client, date="2026-10-28").get_json()["employees"][0]
    assert employee["total_seconds"] == 4200
    assert [s["sem_saida"] for s in employee["sessions"]] == [False, False, True]


def test_orphan_exit_next_day_leaves_employee_outside(admin_client):
    make_employee(admin_client, "AA:01", "R1")
    send(admin_client, "entrada", "2026-10-29T01:00:00Z")  # 22:00 local on the 28th
    send(admin_client, "saida", "2026-10-29T05:00:00Z")  # 02:00 local on the 29th
    first = stay(admin_client, date="2026-10-28").get_json()["employees"][0]
    assert first["sessions"] == [open_("2026-10-29T01:00:00Z")]
    assert first["total_seconds"] == 0
    second = stay(admin_client, date="2026-10-29").get_json()["employees"][0]
    assert second["sessions"] == []
    assert second["total_seconds"] == 0


def test_day_boundary_endpoint_splits_at_local_midnight(admin_client):
    make_employee(admin_client, "AA:01", "R1")
    send(admin_client, "entrada", "2026-10-28T02:59:59Z")  # 23:59:59 on the 27th
    send(admin_client, "entrada", "2026-10-28T03:00:00Z")  # 00:00:00 on the 28th
    previous = stay(admin_client, date="2026-10-27").get_json()["employees"][0]["sessions"]
    current = stay(admin_client, date="2026-10-28").get_json()["employees"][0]["sessions"]
    assert previous == [open_("2026-10-28T02:59:59Z")]
    assert current == [open_("2026-10-28T03:00:00Z")]


def test_utc_output_for_events_sent_with_offset(admin_client):
    make_employee(admin_client, "AA:01", "R1")
    send(admin_client, "entrada", "2026-10-28T09:00:00-03:00")
    send(admin_client, "saida", "2026-10-28T10:00:00-03:00")
    sessions = stay(admin_client, date="2026-10-28").get_json()["employees"][0]["sessions"]
    assert sessions == [closed("2026-10-28T12:00:00Z", "2026-10-28T13:00:00Z", 3600)]


@pytest.mark.parametrize(
    "query",
    [{}, {"date": ""}, {"date": "2026-02-30"}, {"date": "28/10/2026"}]
    + [{"date": "2026-10-28", "employee_id": v} for v in ("abc", "0", "-1", "")],
)
def test_invalid_params(admin_client, query):
    response = stay(admin_client, **query)
    assert response.status_code == 400
    assert response.get_json()["error"]


def test_unknown_employee(admin_client):
    response = stay(admin_client, date="2026-10-28", employee_id=999)
    assert response.status_code == 404
    assert response.get_json() == {"error": "employee not found"}


def test_requires_admin(client):
    # `client` carries the Pi key but no admin session
    assert stay(client, date="2026-10-28").status_code == 401
    assert client.get("/api/stay", headers={"X-API-Key": ""}).status_code == 401
