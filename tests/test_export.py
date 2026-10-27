import csv
import io

import pandas as pd
import pytest

ADMIN_KEY = "test-admin-key"
COLUMNS = ["id", "timestamp", "tipo", "tag_rfid", "colaborador_id", "nome", "matricula"]
ROUTES = ["/api/export/events.csv", "/api/export/events.json"]
ADMIN = {"X-API-Key": ADMIN_KEY}


@pytest.fixture(autouse=True)
def admin_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)


def send(client, id, timestamp="2026-10-27T10:00:00Z", type="entrada", tag="AA:BB"):
    response = client.post(
        "/api/events",
        json={"id": id, "type": type, "rfid_tag": tag, "timestamp": timestamp, "source": "pi-1"},
    )
    assert response.status_code == 201


def make_employee(client, name="José Ação", tag="AA:BB", registration_id="R1"):
    payload = {"name": name, "registration_id": registration_id, "rfid_tag": tag, "role": "dev"}
    return client.post("/api/employees", json=payload).get_json()


def export_csv(client, **query):
    response = client.get("/api/export/events.csv", headers=ADMIN, query_string=query)
    assert response.status_code == 200
    return list(csv.reader(io.StringIO(response.get_data(as_text=True))))


def export_json(client, **query):
    response = client.get("/api/export/events.json", headers=ADMIN, query_string=query)
    assert response.status_code == 200
    return response.get_json()


def test_csv_all_has_header_and_one_row_per_event(client):
    employee = make_employee(client)
    send(client, "e1")
    send(client, "e2", type="saida", timestamp="2026-10-27T11:00:00Z")
    send(client, "e3", type="acesso_negado", timestamp="2026-10-27T12:00:00Z")
    assert export_csv(client) == [
        COLUMNS,
        ["e1", "2026-10-27T10:00:00Z", "entrada", "AA:BB", str(employee["id"]), "José Ação", "R1"],
        ["e2", "2026-10-27T11:00:00Z", "saida", "AA:BB", str(employee["id"]), "José Ação", "R1"],
        ["e3", "2026-10-27T12:00:00Z", "acesso_negado", "AA:BB", str(employee["id"]), "José Ação", "R1"],
    ]


def test_date_filter_is_from_inclusive_to_exclusive(client):
    for hour in (9, 10, 11, 12):
        send(client, f"e{hour}", timestamp=f"2026-10-27T{hour:02d}:00:00Z")
    rows = export_csv(client, **{"from": "2026-10-27T10:00:00Z", "to": "2026-10-27T12:00:00Z"})
    assert [row[0] for row in rows[1:]] == ["e10", "e11"]
    assert [row["id"] for row in export_json(client, **{"from": "2026-10-27T10:00:00Z", "to": "2026-10-27T12:00:00Z"})] == ["e10", "e11"]


def test_new_event_shows_up_in_next_export(client):
    send(client, "e1")
    assert [row[0] for row in export_csv(client)[1:]] == ["e1"]
    send(client, "e2", timestamp="2026-10-27T11:00:00Z")
    assert [row[0] for row in export_csv(client)[1:]] == ["e1", "e2"]
    assert [row["id"] for row in export_json(client)] == ["e1", "e2"]


def test_unknown_tag_keeps_tag_with_empty_employee_fields(client):
    send(client, "e1", type="tentativa_invasao", tag="ZZ:99")
    assert export_csv(client)[1] == ["e1", "2026-10-27T10:00:00Z", "tentativa_invasao", "ZZ:99", "", "", ""]
    assert export_json(client)[0] == {
        "id": "e1",
        "timestamp": "2026-10-27T10:00:00Z",
        "tipo": "tentativa_invasao",
        "tag_rfid": "ZZ:99",
        "colaborador_id": None,
        "nome": None,
        "matricula": None,
    }


def test_deleted_employee_leaves_event_with_empty_employee_fields(client):
    employee = make_employee(client)
    send(client, "e1")
    client.delete(f"/api/employees/{employee['id']}")
    assert export_csv(client)[1] == ["e1", "2026-10-27T10:00:00Z", "entrada", "AA:BB", "", "", ""]


def test_json_matches_csv_fields_and_order(client):
    employee = make_employee(client)
    send(client, "e2", timestamp="2026-10-27T11:00:00Z")
    send(client, "e1")
    send(client, "e3", tag="ZZ:99", timestamp="2026-10-27T12:00:00Z")
    rows = export_json(client)
    assert all(list(row) == COLUMNS for row in rows)
    expected = [
        {"id": "e1", "colaborador_id": employee["id"], "nome": "José Ação", "matricula": "R1"},
        {"id": "e2", "colaborador_id": employee["id"], "nome": "José Ação", "matricula": "R1"},
        {"id": "e3", "colaborador_id": None, "nome": None, "matricula": None},
    ]
    assert [{k: row[k] for k in expected[0]} for row in rows] == expected
    csv_ids = [row[0] for row in export_csv(client)[1:]]
    assert [row["id"] for row in rows] == csv_ids


def test_empty_export_is_header_only_csv_and_empty_json(client):
    send(client, "e1")
    empty = {"from": "2030-01-01T00:00:00Z"}
    assert export_csv(client, **empty) == [COLUMNS]
    assert export_json(client, **empty) == []
    reversed_range = {"from": "2026-10-27T12:00:00Z", "to": "2026-10-27T10:00:00Z"}
    assert export_csv(client, **reversed_range) == [COLUMNS]


def test_order_is_timestamp_ascending_then_insertion(client):
    send(client, "late", timestamp="2026-10-27T12:00:00Z")
    send(client, "tie-b", timestamp="2026-10-27T10:00:00Z")
    send(client, "tie-a", timestamp="2026-10-27T10:00:00Z")
    send(client, "early", timestamp="2026-10-27T09:00:00Z")
    expected = ["early", "tie-b", "tie-a", "late"]
    assert [row[0] for row in export_csv(client)[1:]] == expected
    assert [row["id"] for row in export_json(client)] == expected


def test_pandas_loads_csv_and_json_without_adjustments(client):
    make_employee(client)
    send(client, "e1")
    send(client, "e2", tag="ZZ:99", type="tentativa_invasao", timestamp="2026-10-27T11:00:00-03:00")
    response = client.get("/api/export/events.csv", headers=ADMIN)
    frame = pd.read_csv(io.BytesIO(response.data), parse_dates=["timestamp"])
    assert list(frame.columns) == COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(frame["timestamp"])
    assert str(frame["timestamp"].dt.tz) == "UTC"
    assert frame["timestamp"].tolist() == [
        pd.Timestamp("2026-10-27T10:00:00Z"),
        pd.Timestamp("2026-10-27T14:00:00Z"),
    ]
    assert frame["nome"].tolist()[0] == "José Ação"
    assert pd.isna(frame["nome"].tolist()[1])
    from_json = pd.DataFrame(export_json(client))
    assert list(from_json.columns) == COLUMNS
    assert pd.to_datetime(from_json["timestamp"]).tolist() == frame["timestamp"].tolist()


def test_csv_headers_utf8_without_bom_and_attachment(client):
    make_employee(client)
    send(client, "e1")
    response = client.get("/api/export/events.csv", headers=ADMIN)
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="eventos.csv"'
    assert not response.data.startswith(b"\xef\xbb\xbf")
    assert "José Ação".encode("utf-8") in response.data
    assert b"\r" not in response.data


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": ""}, {"X-API-Key": "wrong"}, {"X-API-Key": "test-pi-key"}])
def test_unauthorized_without_valid_admin_key(client, route, headers):
    make_employee(client)
    send(client, "e1")
    response = client.get(route, headers=headers)
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}
    assert b"AA:BB" not in response.data


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("env_value", [None, ""])
def test_unauthorized_when_admin_key_not_configured(client, monkeypatch, route, env_value):
    send(client, "e1")
    if env_value is None:
        monkeypatch.delenv("ADMIN_API_KEY")
    else:
        monkeypatch.setenv("ADMIN_API_KEY", env_value)
    response = client.get(route, headers={"X-API-Key": env_value or ""})
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("name", ["from", "to"])
@pytest.mark.parametrize("value", ["2026-10-27", "2026-10-27T10:00:00", "ontem", ""])
def test_bad_filter_is_400(client, route, name, value):
    response = client.get(route, headers=ADMIN, query_string={name: value})
    assert response.status_code == 400
    assert response.get_json()["error"]


@pytest.mark.parametrize("route", ROUTES)
def test_bad_filter_accepts_raw_plus_in_offset(client, route):
    send(client, "e1", timestamp="2026-10-27T10:00:00Z")
    response = client.get(f"{route}?from=2026-10-27T11:00:00+01:00", headers=ADMIN)
    assert response.status_code == 200


def test_pi_endpoints_reject_admin_key(client):
    event = {"id": "x", "type": "entrada", "rfid_tag": "AA:BB", "timestamp": "2026-10-27T10:00:00Z", "source": "pi-1"}
    for url, method in (("/api/events", "post"), ("/api/sync/employees", "get")):
        response = getattr(client, method)(url, headers=ADMIN, **({"json": event} if method == "post" else {}))
        assert response.status_code == 401
        assert response.get_json() == {"error": "unauthorized"}
