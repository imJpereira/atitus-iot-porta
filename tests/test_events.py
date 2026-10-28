import sqlite3

import pytest

VALID = {
    "id": "e1",
    "type": "entrada",
    "rfid_tag": "AA:BB",
    "timestamp": "2026-10-27T10:00:00Z",
    "source": "pi-1",
}


@pytest.fixture
def client(admin_client):
    return admin_client


def send(client, **overrides):
    return client.post("/api/events", json={**VALID, **overrides})


def batch(client, events):
    return client.post("/api/events/batch", json={"events": events})


def make_employee(client, tag="AA:BB", registration_id="R1", **extra):
    payload = {"name": "Ana", "registration_id": registration_id, "rfid_tag": tag, "role": "dev"}
    return client.post("/api/employees", json={**payload, **extra}).get_json()


def listed(client, **query):
    return client.get("/api/events", query_string=query).get_json()


def test_create_returns_201_and_stores_fields(client):
    response = send(client)
    assert response.status_code == 201
    body = response.get_json()
    assert {k: body[k] for k in VALID} == VALID
    assert body["employee_id"] is None


def test_timestamp_with_offset_is_stored_as_utc(client):
    body = send(client, timestamp="2026-10-27T07:00:00-03:00").get_json()
    assert body["timestamp"] == "2026-10-27T10:00:00Z"


def test_rfid_tag_is_normalized(client):
    assert send(client, rfid_tag=" aa:bb ").get_json()["rfid_tag"] == "AA:BB"


def test_known_tag_links_employee(client):
    employee = make_employee(client)
    assert send(client, rfid_tag="aa:bb").get_json()["employee_id"] == employee["id"]


def test_unknown_tag_has_no_employee_and_keeps_tag(client):
    body = send(client, rfid_tag="ZZ:99").get_json()
    assert body["employee_id"] is None
    assert body["rfid_tag"] == "ZZ:99"


def test_duplicate_id_is_idempotent(client):
    send(client)
    response = send(client, type="saida", source="pi-2")
    assert response.status_code == 200
    assert response.get_json()["type"] == "entrada"
    assert len(listed(client)) == 1


@pytest.mark.parametrize("event_type", ["entrada", "saida", "acesso_negado", "tentativa_invasao"])
def test_all_event_types_accepted(client, event_type):
    assert send(client, type=event_type).status_code == 201


@pytest.mark.parametrize("bad", ["invasao", "", None, 5])
def test_invalid_type_400(client, bad):
    response = send(client, type=bad)
    assert response.status_code == 400
    assert "type" in response.get_json()["error"]


@pytest.mark.parametrize("field", ["id", "rfid_tag", "source", "timestamp", "type"])
@pytest.mark.parametrize("bad", ["missing", "", "   "])
def test_missing_field_400(client, field, bad):
    payload = {k: v for k, v in VALID.items() if k != field}
    if bad != "missing":
        payload[field] = bad
    response = client.post("/api/events", json=payload)
    assert response.status_code == 400
    assert field in response.get_json()["error"]
    assert listed(client) == []


@pytest.mark.parametrize("bad", ["2026-10-27T10:00:00", "yesterday", 5])
def test_timestamp_without_timezone_or_invalid_400(client, bad):
    response = send(client, timestamp=bad)
    assert response.status_code == 400
    assert "timestamp" in response.get_json()["error"]


@pytest.mark.parametrize("body", [[], "text", 5])
def test_body_not_object_400(client, body):
    assert client.post("/api/events", json=body).status_code == 400


def test_batch_stores_all_with_original_timestamps(client):
    events = [
        {**VALID, "id": "a", "timestamp": "2026-10-27T08:00:00Z"},
        {**VALID, "id": "b", "timestamp": "2026-10-27T09:00:00Z", "type": "saida"},
    ]
    response = batch(client, events)
    assert response.status_code == 200
    assert response.get_json() == {"received": 2, "created": 2}
    assert [e["timestamp"] for e in listed(client)] == [
        "2026-10-27T09:00:00Z",
        "2026-10-27T08:00:00Z",
    ]


def test_batch_with_invalid_event_stores_nothing(client):
    events = [{**VALID, "id": "a"}, {**VALID, "id": "b", "type": "x"}]
    response = batch(client, events)
    assert response.status_code == 400
    assert "events[1]" in response.get_json()["error"]
    assert listed(client) == []


def test_batch_resend_and_inner_duplicates_do_not_duplicate(client):
    events = [{**VALID, "id": "a"}, {**VALID, "id": "a"}, {**VALID, "id": "b"}]
    assert batch(client, events).get_json() == {"received": 3, "created": 2}
    assert batch(client, events).get_json() == {"received": 3, "created": 0}
    assert len(listed(client)) == 2


@pytest.mark.parametrize("body", [[], {}, {"events": "x"}, "text"])
def test_batch_not_a_list_400(client, body):
    assert client.post("/api/events/batch", json=body).status_code == 400


def seed_history(client):
    make_employee(client)
    batch(client, [
        {**VALID, "id": "a", "timestamp": "2026-10-27T08:00:00Z"},
        {**VALID, "id": "b", "timestamp": "2026-10-27T09:00:00Z", "type": "saida"},
        {**VALID, "id": "c", "timestamp": "2026-10-27T10:00:00Z", "rfid_tag": "ZZ", "type": "acesso_negado"},
    ])


def test_list_orders_by_timestamp_desc(client):
    seed_history(client)
    assert [e["id"] for e in listed(client)] == ["c", "b", "a"]


def test_list_filters_by_date_range_from_inclusive_to_exclusive(client):
    seed_history(client)
    ids = [e["id"] for e in listed(client, **{"from": "2026-10-27T09:00:00Z", "to": "2026-10-27T10:00:00Z"})]
    assert ids == ["b"]


def test_list_accepts_unencoded_plus_in_offset(client):
    seed_history(client)
    response = client.get("/api/events?from=2026-10-27T09:00:00+00:00")
    assert [e["id"] for e in response.get_json()] == ["c", "b"]


def test_list_filters_by_type(client):
    seed_history(client)
    assert [e["id"] for e in listed(client, type="saida")] == ["b"]


def test_list_filters_by_employee(client):
    seed_history(client)
    employee_id = client.get("/api/employees").get_json()[0]["id"]
    assert [e["id"] for e in listed(client, employee_id=employee_id)] == ["b", "a"]


def test_list_limit_and_offset(client):
    seed_history(client)
    assert [e["id"] for e in listed(client, limit=1, offset=1)] == ["b"]


@pytest.mark.parametrize("query", [
    {"from": "nope"},
    {"to": "2026-10-27T10:00:00"},
    {"type": "x"},
    {"employee_id": "abc"},
    {"employee_id": 0},
    {"limit": 0},
    {"limit": "x"},
    {"offset": -1},
])
def test_list_invalid_params_400(client, query):
    assert client.get("/api/events", query_string=query).status_code == 400


def test_inside_follows_last_entrada_or_saida(client):
    make_employee(client)
    make_employee(client, tag="CC:DD", registration_id="R2")
    batch(client, [
        {**VALID, "id": "a", "timestamp": "2026-10-27T08:00:00Z"},
        {**VALID, "id": "b", "timestamp": "2026-10-27T09:00:00Z", "type": "saida"},
        {**VALID, "id": "c", "timestamp": "2026-10-27T08:30:00Z", "rfid_tag": "CC:DD"},
    ])
    inside = client.get("/api/events/inside").get_json()
    assert [e["rfid_tag"] for e in inside] == ["CC:DD"]


def test_inside_ignores_denied_and_intrusion_events(client):
    make_employee(client)
    batch(client, [
        {**VALID, "id": "a", "timestamp": "2026-10-27T08:00:00Z"},
        {**VALID, "id": "b", "timestamp": "2026-10-27T09:00:00Z", "type": "acesso_negado"},
        {**VALID, "id": "c", "timestamp": "2026-10-27T09:30:00Z", "type": "tentativa_invasao"},
    ])
    assert len(client.get("/api/events/inside").get_json()) == 1


def test_inside_includes_inactive_employee_and_excludes_unlinked_events(client):
    make_employee(client, is_active=False)
    batch(client, [{**VALID, "id": "a"}, {**VALID, "id": "b", "rfid_tag": "ZZ"}])
    inside = client.get("/api/events/inside").get_json()
    assert [(e["rfid_tag"], e["is_active"]) for e in inside] == [("AA:BB", False)]


def test_deleting_employee_keeps_event_with_null_employee(client):
    employee = make_employee(client)
    send(client)
    client.delete(f"/api/employees/{employee['id']}")
    event = listed(client)[0]
    assert event["employee_id"] is None
    assert event["rfid_tag"] == "AA:BB"


def test_database_enforces_unique_id_and_type(app):
    with sqlite3.connect(app.config["DATABASE"]) as db:
        insert = "INSERT INTO events (id, type, rfid_tag, timestamp, source) VALUES (?, ?, 'T', 'x', 's')"
        db.execute(insert, ("e1", "entrada"))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert, ("e1", "entrada"))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert, ("e2", "invasao"))
