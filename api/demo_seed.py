import csv
import io
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from flask.cli import with_appcontext

from api import ROOT, create_app, get_db
from api.events import insert_event
from api.export import COLUMNS

SEED = 42
SOURCE = "demo_seed"
DEMO_PREFIX = "DEMO-"
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
DAYS = ("2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-26")
CSV_PATH = ROOT / "examples" / "demo_events.csv"

EMPLOYEES = (
    # Authorized and active
    ("Ana Costa (Demo)", "DEMO-001", "DEMO:AA:01", "Character Artist", 1, 1),
    ("Bruno Lima (Demo)", "DEMO-002", "DEMO:AA:02", "3D Modeler", 1, 1),
    ("Carla Souza (Demo)", "DEMO-003", "DEMO:AA:03", "Tech Lead", 1, 1),
    ("Diego Alves (Demo)", "DEMO-004", "DEMO:AA:04", "Concept Artist", 1, 1),
    # Registered without room access (generates acesso_negado)
    ("Elena Rocha (Demo)", "DEMO-005", "DEMO:BB:01", "Marketing", 0, 1),
    ("Fabio Mendes (Demo)", "DEMO-006", "DEMO:BB:02", "QA Tester", 0, 1),
    # Inactive employee (also generates acesso_negado)
    ("Gisele Pires (Demo)", "DEMO-007", "DEMO:BB:03", "Ex-Contractor", 1, 0),
)

AUTHORIZED_TAGS = ("DEMO:AA:01", "DEMO:AA:02", "DEMO:AA:03", "DEMO:AA:04")
# Weighted list so rankings of "who tried the most" have a clear order
DENIED_TAGS = ("DEMO:BB:01", "DEMO:BB:01", "DEMO:BB:01", "DEMO:BB:02", "DEMO:BB:02", "DEMO:BB:03")
INTRUSION_TAGS = ("DEMO:FF:99", "DEMO:FF:99", "DEMO:FF:99", "DEMO:FF:88", "DEMO:FF:88", "DEMO:FF:77")


def utc_iso(day: str, hour: int, minute: int, second: int = 0) -> str:
    local = datetime.strptime(day, "%Y-%m-%d").replace(
        hour=hour, minute=minute, second=second, tzinfo=LOCAL_TZ
    )
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_demo_events(seed: int = SEED) -> list[dict]:
    """Deterministically build >= 5 days of coherent demo events."""
    rng = random.Random(seed)
    events = []
    seq = 0

    def add(day: str, hour: int, minute: int, kind: str, tag: str):
        nonlocal seq
        seq += 1
        second = rng.randint(0, 50)
        events.append({
            "id": f"demo-{day}-{seq:04d}",
            "type": kind,
            "rfid_tag": tag,
            "timestamp": utc_iso(day, hour, minute, second),
            "source": SOURCE,
        })

    for day_idx, day in enumerate(DAYS):
        # Coherent entrada -> saida pairs for authorized employees (morning + afternoon shifts)
        for emp_idx, tag in enumerate(AUTHORIZED_TAGS):
            # Vary attendance slightly by day while keeping multiple employees per day
            if (day_idx + emp_idx) % 5 == 4:
                continue
            in_m = rng.randint(0, 40)
            lunch_out = rng.randint(0, 25)
            lunch_in = rng.randint(30, 55)
            out_m = rng.randint(0, 45)
            add(day, 8 + (emp_idx % 2), in_m, "entrada", tag)
            add(day, 12, lunch_out, "saida", tag)
            add(day, 13, lunch_in, "entrada", tag)
            add(day, 17 + (emp_idx % 2), out_m, "saida", tag)

        # Repeated acesso_negado attempts (3 to 6 per day)
        for _ in range(rng.randint(3, 6)):
            tag = rng.choice(DENIED_TAGS)
            add(day, rng.randint(9, 18), rng.randint(0, 59), "acesso_negado", tag)

        # Repeated tentativa_invasao with unknown tags (2 to 4 per day)
        for _ in range(rng.randint(2, 4)):
            tag = rng.choice(INTRUSION_TAGS)
            add(day, rng.randint(7, 22), rng.randint(0, 59), "tentativa_invasao", tag)

    events.sort(key=lambda e: (e["timestamp"], e["id"]))
    return events


def seed_demo(db=None) -> dict:
    """Idempotently insert demo employees and events. Return counts created."""
    db = db or get_db()
    emp_created = 0
    for name, reg_id, tag, role, access, active in EMPLOYEES:
        cur = db.execute(
            "INSERT OR IGNORE INTO employees "
            "(name, registration_id, rfid_tag, role, has_room_access, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, reg_id, tag, role, access, active),
        )
        emp_created += cur.rowcount == 1
    events = build_demo_events()
    ev_created = sum(insert_event(db, ev) for ev in events)
    db.commit()
    return {
        "employees_created": emp_created,
        "events_total": len(events),
        "events_created": ev_created,
    }


def write_demo_csv(path: Path = CSV_PATH) -> Path:
    """Render current database export rows into a CSV file matching /api/export/events.csv."""
    rows = get_db().execute(
        "SELECT ev.id, ev.timestamp, ev.type AS tipo, ev.rfid_tag AS tag_rfid, "
        "emp.id AS colaborador_id, emp.name AS nome, emp.registration_id AS matricula "
        "FROM events ev LEFT JOIN employees emp ON emp.id = ev.employee_id "
        "ORDER BY ev.timestamp, ev.rowid"
    ).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(tuple(row) for row in rows)
    path.write_text(out.getvalue(), encoding="utf-8", newline="")
    return path


@click.command("seed-demo")
@click.option("--csv-out", type=click.Path(path_type=Path), default=None, help="Optional CSV output path.")
@with_appcontext
def seed_demo_command(csv_out: Path | None):
    """Load reproducible synthetic demo data into the database."""
    stats = seed_demo()
    if csv_out is not None:
        write_demo_csv(csv_out)
    click.echo(
        f"Demo seed: {stats['employees_created']} employees, "
        f"{stats['events_created']}/{stats['events_total']} events created."
    )


def main():
    app = create_app()
    with app.app_context():
        stats = seed_demo()
        write_demo_csv(CSV_PATH)
    print(
        f"Demo seed complete: {stats['employees_created']} new employees, "
        f"{stats['events_created']}/{stats['events_total']} new events. CSV: {CSV_PATH}"
    )


if __name__ == "__main__":
    main()
