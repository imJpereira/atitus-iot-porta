import csv
import io
from collections import Counter

from api.demo_seed import (
    DAYS,
    EMPLOYEES,
    SOURCE,
    build_demo_events,
    seed_demo,
    write_demo_csv,
)
from api.events import EVENT_TYPES
from api.export import COLUMNS


def test_fixed_seed_is_reproducible():
    assert build_demo_events() == build_demo_events()


def test_covers_at_least_five_days_multiple_employees_and_all_four_types(app):
    with app.app_context():
        seed_demo()
    events = build_demo_events()
    days = {ev["timestamp"][:10] for ev in events}
    assert len(days) >= 5
    assert len(DAYS) >= 5
    assert {ev["type"] for ev in events} == set(EVENT_TYPES)
    assert len(EMPLOYEES) >= 4


def test_entrada_and_saida_alternate_coherently_per_employee(app):
    events = build_demo_events()
    by_tag: dict[str, list[str]] = {}
    for ev in events:
        if ev["type"] in ("entrada", "saida"):
            by_tag.setdefault(ev["rfid_tag"], []).append(ev["type"])
    assert len(by_tag) >= 3
    for tag, sequence in by_tag.items():
        assert len(sequence) >= 2
        assert len(sequence) % 2 == 0, f"{tag} left room open"
        for idx, kind in enumerate(sequence):
            expected = "entrada" if idx % 2 == 0 else "saida"
            assert kind == expected, f"{tag} out of order at {idx}"


def test_denied_and_intrusion_tags_repeat_for_ranking():
    events = build_demo_events()
    denied = Counter(ev["rfid_tag"] for ev in events if ev["type"] == "acesso_negado")
    intrusions = Counter(ev["rfid_tag"] for ev in events if ev["type"] == "tentativa_invasao")
    assert max(denied.values()) > 1
    assert len(denied) >= 2
    assert max(intrusions.values()) > 1
    assert len(intrusions) >= 2


def test_synthetic_data_is_clearly_identifiable():
    events = build_demo_events()
    assert all(ev["id"].startswith("demo-") for ev in events)
    assert all(ev["source"] == SOURCE for ev in events)
    assert all(ev["rfid_tag"].startswith("DEMO:") for ev in events)
    assert all(reg.startswith("DEMO-") for _, reg, *_ in EMPLOYEES)


def test_running_twice_does_not_duplicate_records(app, admin_client):
    with app.app_context():
        first = seed_demo()
        second = seed_demo()
    assert first["employees_created"] == len(EMPLOYEES)
    assert first["events_created"] == first["events_total"]
    assert second["employees_created"] == 0
    assert second["events_created"] == 0

    exported = admin_client.get("/api/export/events.json").get_json()
    assert len(exported) == first["events_total"]


def test_exported_csv_and_versioned_file_match_backend_format(app, admin_client, tmp_path):
    csv_file = tmp_path / "demo_events.csv"
    with app.app_context():
        seed_demo()
        write_demo_csv(csv_file)

    response = admin_client.get("/api/export/events.csv")
    assert response.status_code == 200
    assert csv_file.read_text(encoding="utf-8") == response.get_data(as_text=True)

    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0] == list(COLUMNS)
    assert len(rows) > 50


def test_cli_command_is_idempotent(app, tmp_path):
    runner = app.test_cli_runner()
    out_csv = tmp_path / "out.csv"
    res1 = runner.invoke(args=["seed-demo", "--csv-out", str(out_csv)])
    assert res1.exit_code == 0
    assert out_csv.exists()
    res2 = runner.invoke(args=["seed-demo"])
    assert res2.exit_code == 0
    assert "0/" in res2.output
