import sqlite3

import pytest

VALID = {"name": "Ana", "registration_id": "R1", "rfid_tag": "AA:BB", "role": "dev"}
REQUIRED = ["name", "registration_id", "role"]


@pytest.fixture
def client(admin_client):
    return admin_client


def post(client, **overrides):
    return client.post("/api/employees", json={**VALID, **overrides})


def test_create_returns_201_with_id(client):
    response = post(client)
    assert response.status_code == 201
    body = response.get_json()
    assert isinstance(body["id"], int)
    assert {k: body[k] for k in VALID} == VALID


def test_create_defaults_flags(client):
    body = post(client).get_json()
    assert body["has_room_access"] is False
    assert body["is_active"] is True


@pytest.mark.parametrize("field", REQUIRED)
@pytest.mark.parametrize("bad", ["missing", "", "   "])
def test_create_missing_field_400(client, field, bad):
    payload = {k: v for k, v in VALID.items() if k != field}
    if bad != "missing":
        payload[field] = bad
    response = client.post("/api/employees", json=payload)
    assert response.status_code == 400
    assert field in response.get_json()["error"]


def test_create_duplicate_registration_409(client):
    post(client)
    response = post(client, rfid_tag="CC:DD")
    assert response.status_code == 409
    assert "error" in response.get_json()


@pytest.mark.parametrize("field", ["has_room_access", "is_active"])
@pytest.mark.parametrize("bad", [1, "true", None])
def test_flag_not_boolean_400(client, field, bad):
    response = post(client, **{field: bad})
    assert response.status_code == 400
    assert field in response.get_json()["error"]


@pytest.mark.parametrize("body", [[], "text", 5])
def test_body_not_object_400(client, body):
    response = client.post("/api/employees", json=body)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_unknown_field_400(client):
    response = post(client, nickname="x")
    assert response.status_code == 400
    assert "nickname" in response.get_json()["error"]


def test_reserved_fields_are_ignored(client):
    response = post(client, id=99, created_at="x", updated_at="y")
    assert response.status_code == 201
    body = response.get_json()
    assert body["id"] != 99
    assert body["created_at"] != "x"
    assert body["updated_at"] != "y"


def test_invalid_json_400(client):
    response = client.post(
        "/api/employees", data="{not json", content_type="application/json"
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_list_ordered_by_id(client):
    for n in (3, 1, 2):
        post(client, registration_id=f"R{n}", rfid_tag=f"T{n}")
    response = client.get("/api/employees")
    assert response.status_code == 200
    ids = [e["id"] for e in response.get_json()]
    assert len(ids) == 3
    assert ids == sorted(ids)


def test_booleans_are_json_booleans(client):
    created = post(client, has_room_access=True).get_json()
    listed = client.get("/api/employees").get_json()[0]
    fetched = client.get(f"/api/employees/{created['id']}").get_json()
    for employee in (created, listed, fetched):
        assert employee["has_room_access"] is True
        assert employee["is_active"] is True


def test_get_existing_200(client):
    created = post(client).get_json()
    response = client.get(f"/api/employees/{created['id']}")
    assert response.status_code == 200
    assert response.get_json() == created


def test_get_missing_404(client):
    response = client.get("/api/employees/999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_inactive_returned_normally(client):
    created = post(client, is_active=False).get_json()
    assert client.get(f"/api/employees/{created['id']}").get_json()["is_active"] is False
    assert client.get("/api/employees").get_json()[0]["is_active"] is False


def test_patch_updates_only_sent_fields(client):
    created = post(client).get_json()
    response = client.patch(f"/api/employees/{created['id']}", json={"role": "ops"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["role"] == "ops"
    assert {k: body[k] for k in VALID if k != "role"} == {
        k: v for k, v in VALID.items() if k != "role"
    }
    assert client.get(f"/api/employees/{created['id']}").get_json() == body


def test_patch_updates_updated_at(client, app):
    created = post(client).get_json()
    old = "2000-01-01T00:00:00Z"
    with sqlite3.connect(app.config["DATABASE"]) as db:
        db.execute("UPDATE employees SET updated_at = ?", (old,))
    body = client.patch(f"/api/employees/{created['id']}", json={"role": "ops"}).get_json()
    assert body["updated_at"] > old


def test_patch_missing_404(client):
    response = client.patch("/api/employees/999", json={"role": "ops"})
    assert response.status_code == 404
    assert "error" in response.get_json()


@pytest.mark.parametrize("field", REQUIRED)
@pytest.mark.parametrize("bad", ["", "   ", None])
def test_patch_empty_required_400(client, field, bad):
    created = post(client).get_json()
    response = client.patch(f"/api/employees/{created['id']}", json={field: bad})
    assert response.status_code == 400
    assert field in response.get_json()["error"]


def test_patch_duplicate_registration_409(client):
    post(client)
    other = post(client, registration_id="R2", rfid_tag="T2").get_json()
    response = client.patch(f"/api/employees/{other['id']}", json={"registration_id": "R1"})
    assert response.status_code == 409
    assert "error" in response.get_json()


def test_patch_empty_body_unchanged(client):
    created = post(client).get_json()
    response = client.patch(f"/api/employees/{created['id']}", json={})
    assert response.status_code == 200
    assert response.get_json() == created


def test_delete_204(client):
    created = post(client).get_json()
    response = client.delete(f"/api/employees/{created['id']}")
    assert response.status_code == 204
    assert response.data == b""
    assert client.get(f"/api/employees/{created['id']}").status_code == 404


def test_delete_missing_404(client):
    response = client.delete("/api/employees/999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_text_fields_are_stripped(client):
    created = post(client, name="  Ana  ", role=" dev ").get_json()
    assert (created["name"], created["role"]) == ("Ana", "dev")
    patched = client.patch(
        f"/api/employees/{created['id']}", json={"name": "  Bia  "}
    ).get_json()
    assert patched["name"] == "Bia"


@pytest.mark.parametrize("field", ["has_room_access", "is_active"])
@pytest.mark.parametrize("bad", [1, "true", None])
def test_flag_not_boolean_400_on_patch(client, field, bad):
    created = post(client).get_json()
    response = client.patch(f"/api/employees/{created['id']}", json={field: bad})
    assert response.status_code == 400
    assert field in response.get_json()["error"]


@pytest.mark.parametrize("body", [[], "text", 5])
def test_body_not_object_400_on_patch(client, body):
    created = post(client).get_json()
    response = client.patch(f"/api/employees/{created['id']}", json=body)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_unknown_field_400_on_patch(client):
    created = post(client).get_json()
    response = client.patch(f"/api/employees/{created['id']}", json={"nickname": "x"})
    assert response.status_code == 400
    assert "nickname" in response.get_json()["error"]


def test_create_without_rfid_tag_201_and_many_allowed(client):
    for n in (1, 2):
        payload = {k: v for k, v in VALID.items() if k != "rfid_tag"}
        response = client.post("/api/employees", json={**payload, "registration_id": f"R{n}"})
        assert response.status_code == 201
        assert response.get_json()["rfid_tag"] is None


@pytest.mark.parametrize("bad", ["", "   ", 5])
def test_rfid_tag_invalid_400(client, bad):
    response = post(client, rfid_tag=bad)
    assert response.status_code == 400
    assert "rfid_tag" in response.get_json()["error"]


def test_duplicate_rfid_tag_409_names_field(client):
    post(client)
    response = post(client, registration_id="R2")
    assert response.status_code == 409
    assert "rfid_tag" in response.get_json()["error"]
    assert len(client.get("/api/employees").get_json()) == 1


def test_duplicate_registration_409_names_field(client):
    post(client)
    response = post(client, rfid_tag="CC:DD")
    assert "registration_id" in response.get_json()["error"]


def test_rfid_tag_normalized_and_collides_any_case(client):
    assert post(client, rfid_tag=" aa:bb ").get_json()["rfid_tag"] == "AA:BB"
    assert post(client, registration_id="R2", rfid_tag="aa:bb").status_code == 409


def test_patch_duplicate_rfid_tag_409(client):
    post(client)
    other = post(client, registration_id="R2", rfid_tag="T2").get_json()
    response = client.patch(f"/api/employees/{other['id']}", json={"rfid_tag": "aa:bb"})
    assert response.status_code == 409
    assert "rfid_tag" in response.get_json()["error"]


def test_patch_rfid_tag_null_clears(client):
    created = post(client).get_json()
    body = client.patch(f"/api/employees/{created['id']}", json={"rfid_tag": None}).get_json()
    assert body["rfid_tag"] is None


def test_rfid_tag_unique_in_database(app):
    with sqlite3.connect(app.config["DATABASE"]) as db:
        insert = "INSERT INTO employees (name, registration_id, rfid_tag, role) VALUES ('a', ?, 'T', 'r')"
        db.execute(insert, ("R1",))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert, ("R2",))


def test_sync_lists_tagged_including_inactive(client):
    post(client)
    post(client, registration_id="R2", rfid_tag="T2", is_active=False)
    response = client.get("/api/sync/employees")
    assert response.status_code == 200
    body = response.get_json()
    assert [e["rfid_tag"] for e in body] == ["AA:BB", "T2"]
    assert body[1]["is_active"] is False
    assert {"rfid_tag", "has_room_access", "is_active"} <= body[0].keys()


def test_sync_omits_untagged_and_deleted(client):
    payload = {k: v for k, v in VALID.items() if k != "rfid_tag"}
    client.post("/api/employees", json=payload)
    deleted = post(client, registration_id="R2", rfid_tag="T2").get_json()
    client.delete(f"/api/employees/{deleted['id']}")
    assert client.get("/api/sync/employees").get_json() == []


def sync_tags(client):
    return [e["rfid_tag"] for e in client.get("/api/sync/employees").get_json()]


def untagged(client, **overrides):
    payload = {k: v for k, v in VALID.items() if k != "rfid_tag"}
    return client.post("/api/employees", json={**payload, **overrides}).get_json()


def test_patch_links_tag_and_appears_in_sync(client):
    created = untagged(client)
    assert sync_tags(client) == []
    response = client.patch(f"/api/employees/{created['id']}", json={"rfid_tag": " aa:bb "})
    assert response.status_code == 200
    assert response.get_json()["rfid_tag"] == "AA:BB"
    assert sync_tags(client) == ["AA:BB"]


def test_swap_tag_old_disappears_from_sync(client):
    created = post(client).get_json()
    client.patch(f"/api/employees/{created['id']}", json={"rfid_tag": "NEW"})
    assert sync_tags(client) == ["NEW"]


def test_unlink_tag_leaves_sync(client):
    created = post(client).get_json()
    client.patch(f"/api/employees/{created['id']}", json={"rfid_tag": None})
    assert sync_tags(client) == []


def test_permission_and_status_in_sync(client):
    created = post(client).get_json()
    client.patch(f"/api/employees/{created['id']}", json={"has_room_access": True, "is_active": False})
    [synced] = client.get("/api/sync/employees").get_json()
    assert synced["has_room_access"] is True
    assert synced["is_active"] is False


def test_migration_002_preserves_data(tmp_path):
    from pathlib import Path

    import api

    path = tmp_path / "old.db"
    migrations = Path(api.__file__).parent / "migrations"
    with sqlite3.connect(path) as db:
        db.executescript((migrations / "001_employees.sql").read_text())
        db.execute("CREATE TABLE schema_migrations (name TEXT PRIMARY KEY)")
        db.execute("INSERT INTO schema_migrations VALUES ('001_employees.sql')")
        db.execute(
            "INSERT INTO employees (name, registration_id, rfid_tag, role, is_active)"
            " VALUES ('Ana', 'R1', 'T1', 'dev', 0)"
        )
    api.migrate(path)
    row = sqlite3.connect(path).execute(
        "SELECT name, registration_id, rfid_tag, role, is_active FROM employees"
    ).fetchone()
    assert row == ("Ana", "R1", "T1", "dev", 0)


def owner_of(employee):
    return {k: employee[k] for k in ("id", "name", "registration_id")}


def test_patch_duplicate_rfid_tag_409_names_owner(client):
    owner = post(client).get_json()
    other = post(client, registration_id="R2", rfid_tag="T2").get_json()
    response = client.patch(f"/api/employees/{other['id']}", json={"rfid_tag": " aa:bb "})
    assert response.status_code == 409
    body = response.get_json()
    assert body == {"error": "rfid_tag already exists", "owner": owner_of(owner)}
    assert client.get(f"/api/employees/{other['id']}").get_json() == other
    assert client.get(f"/api/employees/{owner['id']}").get_json() == owner


def test_post_duplicate_rfid_tag_409_names_owner(client):
    owner = post(client).get_json()
    response = post(client, registration_id="R2")
    assert response.status_code == 409
    assert response.get_json() == {"error": "rfid_tag already exists", "owner": owner_of(owner)}
    assert len(client.get("/api/employees").get_json()) == 1


def test_duplicate_registration_409_has_no_owner(client):
    post(client)
    other = post(client, registration_id="R2", rfid_tag="T2").get_json()
    # other's own tag is looked up on conflict; registration_id conflicts must not leak it as owner
    response = client.patch(f"/api/employees/{other['id']}", json={"registration_id": "R1"})
    assert response.status_code == 409
    assert response.get_json() == {"error": "registration_id already exists"}
    response = post(client, rfid_tag="CC:DD")
    assert response.get_json() == {"error": "registration_id already exists"}


def test_patch_own_tag_200(client):
    created = post(client).get_json()
    response = client.patch(f"/api/employees/{created['id']}", json={"rfid_tag": " aa:bb "})
    assert response.status_code == 200
    assert response.get_json() == created
