from datetime import datetime, timezone
import json
from uuid import UUID

from rasp.access import (
    AccessController,
    build_event,
    emit_feedback,
    fetch_employees,
    run_access_loop,
    send_event,
)
from rasp.test_hardware import DEFAULT_PINS
from tests.test_hardware import FakeGPIO
from tests.test_rfid import SequenceReader


EMPLOYEES = [
    {"id": 1, "name": "Ana Silva", "rfid_tag": "TAG-ATIVA", "is_active": True, "has_room_access": True},
    {"id": 2, "name": "Bruno Costa", "rfid_tag": "TAG-SEM-ACESSO", "is_active": True, "has_room_access": False},
    {"id": 3, "name": "Carlos Souza", "rfid_tag": "TAG-INATIVA", "is_active": False, "has_room_access": True},
]


def clear_pin_env(monkeypatch):
    for key in DEFAULT_PINS:
        monkeypatch.delenv(key, raising=False)


def outputs_for(gpio: FakeGPIO) -> list[tuple[int, int]]:
    return [(pin, val) for kind, pin, val, *_ in [e + (None,) for e in gpio.events if e[0] == "output"]]


def test_four_cases_messages_events_and_distinct_gpio_patterns(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    moments = [
        datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 13, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 15, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 16, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 17, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 18, 0, 0, tzinfo=timezone.utc),
    ]
    gpio = FakeGPIO()
    messages: list[str] = []
    sent_events: list[dict] = []

    controller = AccessController(
        EMPLOYEES,
        gpio=gpio,
        clock=lambda: moments.pop(0),
        sleep=lambda _: None,
        display=messages.append,
        sender=sent_events.append,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
    )

    # Caso 1: primeira entrada do dia
    r1 = controller.handle_tag(" tag-ativa ")
    assert r1["case"] == "first_entry"
    assert r1["message"] == "Bem-vindo, Ana Silva"
    assert r1["event"]["type"] == "entrada"
    assert r1["event"]["rfid_tag"] == "TAG-ATIVA"
    assert r1["event"]["timestamp"] == "2026-10-28T12:00:00Z"
    UUID(r1["event"]["id"])
    p1 = outputs_for(gpio)
    gpio.events.clear()

    # Saída intermediária para permitir retorno no mesmo dia
    r_exit = controller.handle_tag("TAG-ATIVA")
    assert r_exit["event"]["type"] == "saida"
    assert r_exit["message"] == "Até logo, Ana Silva"
    gpio.events.clear()

    # Caso 2: já entrou no dia e estava fora -> retorno
    r2 = controller.handle_tag("TAG-ATIVA")
    assert r2["case"] == "return_entry"
    assert r2["message"] == "Bem-vindo de volta, Ana Silva"
    assert r2["event"]["type"] == "entrada"
    p2 = outputs_for(gpio)
    gpio.events.clear()

    # Caso 3a: colaborador sem permissão de sala
    r3 = controller.handle_tag("tag-sem-acesso")
    assert r3["case"] == "access_denied"
    assert r3["message"] == "Acesso negado, Bruno Costa"
    assert r3["event"]["type"] == "acesso_negado"
    p3 = outputs_for(gpio)
    gpio.events.clear()

    # Caso 3b: colaborador inativo
    r3_inativo = controller.handle_tag("tag-inativa")
    assert r3_inativo["case"] == "access_denied"
    assert r3_inativo["message"] == "Acesso negado, Carlos Souza"
    assert r3_inativo["event"]["type"] == "acesso_negado"
    gpio.events.clear()

    # Caso 4: tag não cadastrada -> tentativa de invasão
    r4 = controller.handle_tag("ff:ee:dd")
    assert r4["case"] == "intrusion"
    assert "FF:EE:DD" in r4["message"]
    assert r4["event"]["type"] == "tentativa_invasao"
    p4 = outputs_for(gpio)

    # Os 4 padrões de LED + buzzer são distintos entre si
    assert len({tuple(p1), tuple(p2), tuple(p3), tuple(p4)}) == 4
    # E cada caso aciona o LED correspondente e o buzzer (14)
    assert (12, 1) in p1 and (14, 1) in p1  # Verde + Buzzer (1 pulso)
    assert p1.count((12, 1)) == 1
    assert p2.count((12, 1)) == 2 and p2.count((14, 1)) == 2  # Verde + Buzzer (2 pulsos)
    assert p3.count((16, 1)) == 2 and p3.count((14, 1)) == 2  # Amarelo + Buzzer (2 pulsos)
    assert p4.count((21, 1)) == 3 and p4.count((14, 1)) == 3  # Vermelho + Buzzer (3 pulsos)

    assert len(sent_events) == 6
    assert messages == [
        "Bem-vindo, Ana Silva",
        "Até logo, Ana Silva",
        "Bem-vindo de volta, Ana Silva",
        "Acesso negado, Bruno Costa",
        "Acesso negado, Carlos Souza",
        "Alerta de invasão: tag não cadastrada (FF:EE:DD)",
    ]


def test_first_entry_rule_uses_local_date_and_resets_next_day(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    # 2026-10-28 23:30 em America/Sao_Paulo = 2026-10-29 02:30Z (ainda dia 28 local)
    # 2026-10-29 00:10 em America/Sao_Paulo = 2026-10-29 03:10Z (virou para dia 29 local)
    moments = [
        datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 18, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 29, 2, 30, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 29, 3, 10, 0, tzinfo=timezone.utc),
    ]
    controller = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: moments.pop(0),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda _: None,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
    )

    first = controller.handle_tag("TAG-ATIVA")
    exit_same_day = controller.handle_tag("TAG-ATIVA")
    same_local_day = controller.handle_tag("TAG-ATIVA")
    next_local_day = controller.handle_tag("TAG-ATIVA")

    assert first["case"] == "first_entry"
    assert exit_same_day["event"]["type"] == "saida"
    assert same_local_day["case"] == "return_entry"
    assert same_local_day["event"]["type"] == "entrada"
    # Na virada do dia, quem ainda constava dentro (depois de same_local_day) volta para fora
    assert next_local_day["case"] == "first_entry"
    assert next_local_day["event"]["type"] == "entrada"
    assert next_local_day["message"] == "Bem-vindo, Ana Silva"


def test_multiple_sessions_and_day_rollover_reset(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    moments = [
        datetime(2026, 10, 28, 11, 0, 0, tzinfo=timezone.utc),  # sessão 1: entrada
        datetime(2026, 10, 28, 15, 0, 0, tzinfo=timezone.utc),  # sessão 1: saída
        datetime(2026, 10, 28, 16, 0, 0, tzinfo=timezone.utc),  # sessão 2: entrada
        datetime(2026, 10, 28, 20, 0, 0, tzinfo=timezone.utc),  # sessão 2: saída
        datetime(2026, 10, 28, 22, 0, 0, tzinfo=timezone.utc),  # sessão 3: entrada (fica dentro)
        datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc),  # dia seguinte: reinicia fora -> entrada
    ]
    events: list[dict] = []
    controller = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: moments.pop(0),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=events.append,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
    )

    for _ in range(5):
        controller.handle_tag("TAG-ATIVA")
    assert "TAG-ATIVA" in controller.inside

    # Virou o dia com colaborador dentro -> reinicia para fora e registra nova entrada
    r_next_day = controller.handle_tag("TAG-ATIVA")
    assert r_next_day["event"]["type"] == "entrada"
    assert r_next_day["case"] == "first_entry"
    assert "TAG-ATIVA" in controller.inside

    assert [e["type"] for e in events] == [
        "entrada",
        "saida",
        "entrada",
        "saida",
        "entrada",
        "entrada",
    ]


def test_persisted_state_recovers_after_restart(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    state_file = tmp_path / "rasp_state.json"
    env_file = tmp_path / "no.env"

    # 1ª instância: Ana entra e permanece dentro
    c1 = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda _: None,
        env_path=env_file,
        state_path=state_file,
    )
    r1 = c1.handle_tag("TAG-ATIVA")
    assert r1["event"]["type"] == "entrada"
    assert state_file.is_file()

    # 2ª instância (simulando reinício da Pi no mesmo dia): recupera que Ana está dentro
    c2 = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: datetime(2026, 10, 28, 14, 0, 0, tzinfo=timezone.utc),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda _: None,
        env_path=env_file,
        state_path=state_file,
    )
    assert "TAG-ATIVA" in c2.inside
    r2 = c2.handle_tag("TAG-ATIVA")
    assert r2["event"]["type"] == "saida"
    assert "TAG-ATIVA" not in c2.inside

    # 3ª instância (reinício ainda no mesmo dia após saída): próxima leitura é reentrada ("return_entry")
    c3 = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: datetime(2026, 10, 28, 16, 0, 0, tzinfo=timezone.utc),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda _: None,
        env_path=env_file,
        state_path=state_file,
    )
    assert "TAG-ATIVA" not in c3.inside
    assert "TAG-ATIVA" in c3.entered_today
    r3 = c3.handle_tag("TAG-ATIVA")
    assert r3["event"]["type"] == "entrada"
    assert r3["case"] == "return_entry"


def test_gpio_pins_configurable_by_env(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GPIO_LED_GREEN=5\nGPIO_LED_YELLOW=6\nGPIO_LED_RED=13\nGPIO_BUZZER=19\n",
        encoding="utf-8",
    )
    gpio = FakeGPIO()
    emit_feedback("intrusion", gpio=gpio, sleep=lambda _: None, env_path=env_file)

    outputs = outputs_for(gpio)
    assert (13, 1) in outputs
    assert (19, 1) in outputs
    assert all(pin in (13, 19) for pin, _ in outputs)


def test_send_event_and_fetch_employees_use_backend_contract(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PI_API_KEY=secret-pi\nAPI_BASE_URL=http://api.local:5000/\n", encoding="utf-8")
    monkeypatch.delenv("PI_API_KEY", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)

    captured = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=0):
        captured.append((req.full_url, req.get_method(), dict(req.header_items()), req.data))
        if req.full_url.endswith("/api/sync/employees"):
            return FakeResponse(EMPLOYEES)
        return FakeResponse({"id": "123", "status": "created"})

    employees = fetch_employees(urlopen=fake_urlopen, env_path=env_file)
    assert len(employees) == 3
    assert captured[0][0] == "http://api.local:5000/api/sync/employees"
    assert captured[0][2]["X-api-key"] == "secret-pi"

    ev = build_event("TAG-ATIVA", "entrada", datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc))
    resp = send_event(ev, urlopen=fake_urlopen, env_path=env_file)
    assert resp["status"] == "created"
    assert captured[1][0] == "http://api.local:5000/api/events"
    assert captured[1][1] == "POST"
    assert captured[1][2]["X-api-key"] == "secret-pi"
    sent_body = json.loads(captured[1][3].decode("utf-8"))
    assert sent_body == ev


def test_run_access_loop_integrates_with_rfid_reader(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    reader = SequenceReader(["tag-ativa", "tag-ativa", "desconhecida"])
    sent: list[dict] = []
    controller = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=sent.append,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
    )

    run_access_loop(
        controller=controller,
        reader=reader,
        debounce_seconds=3.0,
        poll_interval=0,
        max_iterations=3,
        env_path=tmp_path / "no.env",
    )

    # Segunda leitura de tag-ativa está dentro do debounce de 3s -> ignorada
    assert [(e["rfid_tag"], e["type"]) for e in sent] == [
        ("TAG-ATIVA", "entrada"),
        ("DESCONHECIDA", "tentativa_invasao"),
    ]
