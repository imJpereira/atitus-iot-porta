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
    send_events_batch,
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


def test_startup_online_saves_local_cache_with_updated_at(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    cache_file = tmp_path / "employees_cache.json"
    moment = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)

    controller = AccessController(
        gpio=FakeGPIO(),
        clock=lambda: moment,
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda _: None,
        fetcher=lambda: EMPLOYEES,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
        cache_path=cache_file,
    )

    assert controller.has_cache is True
    assert controller.updated_at == "2026-10-28T12:00:00Z"
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved == {"updated_at": "2026-10-28T12:00:00Z", "employees": EMPLOYEES}

    res = controller.handle_tag("TAG-ATIVA")
    assert res["case"] == "first_entry"
    assert res["event"]["type"] == "entrada"


def test_startup_offline_with_existing_cache_operates_normally(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    cache_file = tmp_path / "employees_cache.json"
    cache_file.write_text(
        json.dumps({"updated_at": "2026-10-28T10:00:00Z", "employees": EMPLOYEES}),
        encoding="utf-8",
    )

    def offline_fetcher():
        raise OSError("network unreachable")

    controller = AccessController(
        gpio=FakeGPIO(),
        clock=lambda: datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda _: None,
        fetcher=offline_fetcher,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
        cache_path=cache_file,
    )

    assert controller.has_cache is True
    assert controller.updated_at == "2026-10-28T10:00:00Z"
    res = controller.handle_tag("TAG-ATIVA")
    assert res["case"] == "first_entry"
    assert res["message"] == "Bem-vindo, Ana Silva"


def test_startup_offline_without_cache_denies_all_logs_and_reconnects(monkeypatch, tmp_path, caplog):
    clear_pin_env(monkeypatch)
    cache_file = tmp_path / "employees_cache.json"
    online = False

    def flaky_fetcher():
        if not online:
            raise OSError("offline")
        return EMPLOYEES

    moments = iter([
        datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),  # init sync attempt
        datetime(2026, 10, 28, 12, 0, 5, tzinfo=timezone.utc),  # 1st tag read (still offline)
        datetime(2026, 10, 28, 12, 0, 10, tzinfo=timezone.utc),  # 2nd tag read (back online)
    ])
    messages: list[str] = []

    controller = AccessController(
        gpio=FakeGPIO(),
        clock=lambda: next(moments),
        sleep=lambda _: None,
        display=messages.append,
        sender=lambda _: None,
        fetcher=flaky_fetcher,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
        cache_path=cache_file,
    )

    assert controller.has_cache is False
    assert not cache_file.exists()

    # Sem cache e sem rede -> nega qualquer tag e sinaliza no log e no display
    denied = controller.handle_tag("TAG-ATIVA")
    assert denied["case"] == "access_denied"
    assert denied["event"]["type"] == "acesso_negado"
    assert "cache local indisponível" in denied["message"]
    assert "não validável" in caplog.text

    # Rede volta -> reconecta ao ler próxima tag, salva cache e libera acesso
    online = True
    allowed = controller.handle_tag("TAG-ATIVA")
    assert controller.has_cache is True
    assert cache_file.is_file()
    assert allowed["case"] == "first_entry"
    assert allowed["event"]["type"] == "entrada"


def test_periodic_sync_applies_permission_changes_and_preserves_cache_on_failure(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("CACHE_SYNC_INTERVAL_SECONDS=30\n", encoding="utf-8")
    monkeypatch.delenv("CACHE_SYNC_INTERVAL_SECONDS", raising=False)
    cache_file = tmp_path / "employees_cache.json"

    current_employees = [
        {"id": 2, "name": "Bruno Costa", "rfid_tag": "TAG-SEM-ACESSO", "is_active": True, "has_room_access": False},
    ]
    should_fail = False
    fetch_calls = 0

    def dynamic_fetcher():
        nonlocal fetch_calls
        fetch_calls += 1
        if should_fail:
            raise OSError("timeout")
        return list(current_employees)

    moments = iter([
        datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),   # init sync (t=0s)
        datetime(2026, 10, 28, 12, 0, 10, tzinfo=timezone.utc),  # t=10s (<30s, sem novo sync)
        datetime(2026, 10, 28, 12, 0, 35, tzinfo=timezone.utc),  # t=35s (>=30s, aplica nova permissão)
        datetime(2026, 10, 28, 12, 1, 10, tzinfo=timezone.utc),  # t=70s (>=30s, falha mas preserva cache)
    ])

    controller = AccessController(
        gpio=FakeGPIO(),
        clock=lambda: next(moments),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda _: None,
        fetcher=dynamic_fetcher,
        env_path=env_file,
        state_path=tmp_path / "state.json",
        cache_path=cache_file,
    )
    assert controller.sync_interval == 30.0
    assert fetch_calls == 1

    # Admin libera acesso no backend, mas aos t=10s ainda usa o cache antigo
    current_employees = [
        {"id": 2, "name": "Bruno Costa", "rfid_tag": "TAG-SEM-ACESSO", "is_active": True, "has_room_access": True},
    ]
    r_before = controller.handle_tag("TAG-SEM-ACESSO")
    assert r_before["case"] == "access_denied"
    assert fetch_calls == 1

    # Aos t=35s o intervalo de 30s expirou -> atualiza cache e aplica a nova permissão
    r_after = controller.handle_tag("TAG-SEM-ACESSO")
    assert fetch_calls == 2
    assert r_after["case"] == "first_entry"
    assert controller.updated_at == "2026-10-28T12:00:35Z"

    # Aos t=70s o backend cai -> falha na atualização não apaga o cache anterior (nem memória nem disco)
    should_fail = True
    r_offline = controller.handle_tag("TAG-SEM-ACESSO")
    assert fetch_calls == 3
    assert r_offline["event"]["type"] == "saida"
    assert controller.updated_at == "2026-10-28T12:00:35Z"
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["updated_at"] == "2026-10-28T12:00:35Z"
    assert saved["employees"][0]["has_room_access"] is True


def test_offline_event_queued_with_original_uuid_timestamp_and_immediate_feedback(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    queue_file = tmp_path / "events_queue.json"
    gpio = FakeGPIO()
    order: list[str] = []

    def tracking_sleep(_seconds: float) -> None:
        if "feedback" not in order:
            order.append("feedback")

    def failing_sender(_event: dict) -> None:
        order.append("sender")
        raise OSError("connection refused")

    moment = datetime(2026, 10, 28, 14, 30, 0, tzinfo=timezone.utc)
    controller = AccessController(
        EMPLOYEES,
        gpio=gpio,
        clock=lambda: moment,
        sleep=tracking_sleep,
        display=lambda _: order.append("display"),
        sender=failing_sender,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
        queue_path=queue_file,
    )

    res = controller.handle_tag("tag-ativa")
    # Feedback visual/sonoro e mensagem ocorrem antes da tentativa de envio ao backend
    assert order == ["display", "feedback", "sender"]
    assert (12, 1) in outputs_for(gpio) and (14, 1) in outputs_for(gpio)

    # Evento salvo na fila em memória e em disco com UUID, tipo, tag e timestamp originais
    assert len(controller.pending_events) == 1
    queued = controller.pending_events[0]
    assert queued == res["event"]
    UUID(queued["id"])
    assert queued["rfid_tag"] == "TAG-ATIVA"
    assert queued["type"] == "entrada"
    assert queued["timestamp"] == "2026-10-28T14:30:00Z"
    assert queued["source"] == "raspberry_pi"

    on_disk = json.loads(queue_file.read_text(encoding="utf-8"))
    assert on_disk == [queued]


def test_pending_events_persist_across_controller_restarts(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    queue_file = tmp_path / "events_queue.json"
    state_file = tmp_path / "state.json"
    env_file = tmp_path / "no.env"

    def failing_sender(_ev: dict) -> None:
        raise OSError("network down")

    c1 = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=failing_sender,
        env_path=env_file,
        state_path=state_file,
        queue_path=queue_file,
    )
    r1 = c1.handle_tag("TAG-ATIVA")
    r2 = c1.handle_tag("FF:EE:DD")
    assert len(c1.pending_events) == 2

    # Reinicializa o controlador com eventos pendentes e grava mais um evento offline
    c2 = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: datetime(2026, 10, 28, 12, 5, 0, tzinfo=timezone.utc),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=failing_sender,
        env_path=env_file,
        state_path=state_file,
        queue_path=queue_file,
    )
    assert c2.pending_events == [r1["event"], r2["event"]]

    r3 = c2.handle_tag("TAG-ATIVA")
    assert c2.pending_events == [r1["event"], r2["event"], r3["event"]]
    saved = json.loads(queue_file.read_text(encoding="utf-8"))
    assert [e["id"] for e in saved] == [r1["event"]["id"], r2["event"]["id"], r3["event"]["id"]]


def test_queue_limit_logs_warning_without_discarding_events(monkeypatch, tmp_path, caplog):
    clear_pin_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("EVENT_QUEUE_MAX_SIZE=2\n", encoding="utf-8")
    monkeypatch.delenv("EVENT_QUEUE_MAX_SIZE", raising=False)
    queue_file = tmp_path / "events_queue.json"

    moments = iter([
        datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 12, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 12, 2, 0, tzinfo=timezone.utc),
    ])

    def failing_sender(_ev: dict) -> None:
        raise OSError("offline")

    controller = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: next(moments),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=failing_sender,
        env_path=env_file,
        state_path=tmp_path / "state.json",
        queue_path=queue_file,
    )
    assert controller.queue_max_size == 2

    e1 = controller.handle_tag("TAG-ATIVA")["event"]
    assert "limite configurado: 2" not in caplog.text

    e2 = controller.handle_tag("TAG-SEM-ACESSO")["event"]
    assert "Fila local de eventos atingiu 2 itens (limite configurado: 2)" in caplog.text

    e3 = controller.handle_tag("FF:EE:DD")["event"]
    assert "Fila local de eventos atingiu 3 itens (limite configurado: 2)" in caplog.text

    # Nenhum evento antigo ou novo é descartado
    assert controller.pending_events == [e1, e2, e3]
    assert json.loads(queue_file.read_text(encoding="utf-8")) == [e1, e2, e3]


def test_reconnect_flushes_queue_in_chronological_order_and_handles_midway_failure(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("EVENT_SYNC_INTERVAL_SECONDS=10\nEVENT_SYNC_BATCH_SIZE=2\n", encoding="utf-8")
    monkeypatch.delenv("EVENT_SYNC_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("EVENT_SYNC_BATCH_SIZE", raising=False)
    queue_file = tmp_path / "events_queue.json"

    online = False
    fail_second_batch = True
    received_batches: list[list[dict]] = []

    def flaky_single_sender(event: dict) -> None:
        if not online:
            raise OSError("offline")
        received_batches.append([event])

    def flaky_batch_sender(batch: list[dict]) -> None:
        nonlocal fail_second_batch
        if not online:
            raise OSError("offline")
        if len(received_batches) == 1 and fail_second_batch:
            fail_second_batch = False
            raise OSError("connection reset during 2nd batch")
        received_batches.append(list(batch))

    t0 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
    moments = iter([
        datetime(2026, 10, 28, 12, 0, 1, tzinfo=timezone.utc),   # e1 (offline)
        datetime(2026, 10, 28, 12, 0, 2, tzinfo=timezone.utc),   # e2 (offline)
        datetime(2026, 10, 28, 12, 0, 3, tzinfo=timezone.utc),   # e3 (offline)
    ])

    controller = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: next(moments, t0),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=flaky_single_sender,
        batch_sender=flaky_batch_sender,
        env_path=env_file,
        state_path=tmp_path / "state.json",
        queue_path=queue_file,
    )
    assert controller.event_sync_interval == 10.0
    assert controller.event_sync_batch_size == 2

    e1 = controller.handle_tag("TAG-ATIVA")["event"]
    e2 = controller.handle_tag("TAG-SEM-ACESSO")["event"]
    e3 = controller.handle_tag("FF:EE:DD")["event"]
    assert [e["id"] for e in controller.pending_events] == [e1["id"], e2["id"], e3["id"]]

    # Tentativa antes do intervalo de 10s (aos t=8s) -> não tenta reenviar ainda
    controller.maybe_sync(datetime(2026, 10, 28, 12, 0, 8, tzinfo=timezone.utc), max_batches=None)
    assert received_batches == []
    assert len(controller.pending_events) == 3

    # Conexão volta aos t=15s (>= 10s): 1º lote [e1, e2] confirma, 2º lote [e3] falha no meio
    online = True
    controller.maybe_sync(datetime(2026, 10, 28, 12, 0, 15, tzinfo=timezone.utc), max_batches=None)
    assert received_batches == [[e1, e2]]
    assert controller.pending_events == [e3]
    assert json.loads(queue_file.read_text(encoding="utf-8")) == [e3]

    # Antes de 10s desde a falha (aos t=20s) -> aguarda intervalo
    controller.maybe_sync(datetime(2026, 10, 28, 12, 0, 20, tzinfo=timezone.utc), max_batches=None)
    assert controller.pending_events == [e3]

    # Após 10s desde a falha (aos t=26s) -> reenvia o restante [e3] e limpa a fila
    controller.maybe_sync(datetime(2026, 10, 28, 12, 0, 26, tzinfo=timezone.utc), max_batches=None)
    assert received_batches == [[e1, e2], [e3]]
    assert controller.pending_events == []
    assert json.loads(queue_file.read_text(encoding="utf-8")) == []


def test_new_badge_reads_are_served_during_background_sync_in_loop(monkeypatch, tmp_path):
    clear_pin_env(monkeypatch)
    queue_file = tmp_path / "events_queue.json"
    e1 = build_event("TAG-ATIVA", "entrada", datetime(2026, 10, 28, 11, 58, 0, tzinfo=timezone.utc), event_id="ev-1")
    e2 = build_event("TAG-ATIVA", "saida", datetime(2026, 10, 28, 11, 59, 0, tzinfo=timezone.utc), event_id="ev-2")
    queue_file.write_text(json.dumps([e1, e2]), encoding="utf-8")

    # Na inicialização ainda está offline; fica online durante o loop
    online = False
    timeline: list[str] = []

    def batch_sender(batch: list[dict]) -> None:
        if not online:
            raise OSError("offline on init")
        for ev in batch:
            timeline.append(f"sync:{ev['id']}")

    def single_sender(ev: dict) -> None:
        timeline.append(f"live:{ev['id']}")

    moments = iter([
        datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),   # init sync fails
        datetime(2026, 10, 28, 12, 0, 15, tzinfo=timezone.utc),  # tick 1 -> sends batch 1 (ev-1)
        datetime(2026, 10, 28, 12, 0, 16, tzinfo=timezone.utc),  # read 1 during sync -> TAG-ATIVA
        datetime(2026, 10, 28, 12, 0, 17, tzinfo=timezone.utc),  # tick 2 -> sends batch 2 (ev-2)
        datetime(2026, 10, 28, 12, 0, 18, tzinfo=timezone.utc),  # tick 3 -> sends batch 3 (new tag read)
    ])

    controller = AccessController(
        EMPLOYEES,
        gpio=FakeGPIO(),
        clock=lambda: next(moments),
        sleep=lambda _: None,
        display=lambda msg: timeline.append(f"display:{msg}"),
        sender=single_sender,
        batch_sender=batch_sender,
        event_sync_interval=10.0,
        event_sync_batch_size=1,
        env_path=tmp_path / "no.env",
        state_path=tmp_path / "state.json",
        queue_path=queue_file,
    )
    assert len(controller.pending_events) == 2

    online = True
    reader = SequenceReader(["TAG-ATIVA", None, None])
    run_access_loop(
        controller=controller,
        reader=reader,
        debounce_seconds=3.0,
        poll_interval=0,
        max_iterations=3,
        env_path=tmp_path / "no.env",
    )

    # Durante a sincronização por lotes (1 por tick), a leitura do crachá no tick 1 foi atendida imediatamente
    assert timeline[0] == "sync:ev-1"
    assert timeline[1] == "display:Bem-vindo, Ana Silva"
    assert timeline[2] == "sync:ev-2"
    assert timeline[3].startswith("sync:")
    assert controller.pending_events == []


def test_e2e_offline_to_online_sync_and_idempotency_with_flask_api(monkeypatch, tmp_path, app, admin_client):
    clear_pin_env(monkeypatch)
    monkeypatch.setenv("PI_API_KEY", "test-pi-key")
    env_file = tmp_path / ".env"
    env_file.write_text("PI_API_KEY=test-pi-key\nAPI_BASE_URL=http://local.test\n", encoding="utf-8")
    queue_file = tmp_path / "events_queue.json"
    cache_file = tmp_path / "employees_cache.json"
    state_file = tmp_path / "state.json"

    # Cadastra colaboradora na API real (SQLite)
    emp = admin_client.post(
        "/api/employees",
        json={"name": "Ana Silva", "registration_id": "MAT-01", "rfid_tag": "TAG-ATIVA", "role": "Eng", "has_room_access": True},
    ).get_json()

    backend_up = True

    class ClientResponse:
        def __init__(self, resp):
            self.resp = resp

        def read(self):
            return self.resp.get_data()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def flask_urlopen(req, timeout=0):
        if not backend_up:
            raise OSError("backend down")
        path = req.full_url.removeprefix("http://local.test")
        headers = {k: v for k, v in req.header_items()}
        with app.test_client() as c:
            resp = c.open(path, method=req.get_method(), headers=headers, data=req.data)
        if resp.status_code >= 400:
            raise OSError(f"HTTP {resp.status_code}")
        return ClientResponse(resp)

    moments = iter([
        datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),   # startup cache sync (online)
        datetime(2026, 10, 28, 12, 1, 0, tzinfo=timezone.utc),   # 1st badge offline (entrada Ana)
        datetime(2026, 10, 28, 12, 2, 0, tzinfo=timezone.utc),   # 2nd badge offline (invasão FF:EE:DD)
        datetime(2026, 10, 28, 12, 3, 0, tzinfo=timezone.utc),   # 3rd badge offline (saída Ana)
        datetime(2026, 10, 28, 12, 4, 0, tzinfo=timezone.utc),   # reconnect sync
    ])

    controller = AccessController(
        gpio=FakeGPIO(),
        clock=lambda: next(moments),
        sleep=lambda _: None,
        display=lambda _: None,
        sender=lambda ev: send_event(ev, urlopen=flask_urlopen, env_path=env_file),
        batch_sender=lambda batch: send_events_batch(batch, urlopen=flask_urlopen, env_path=env_file),
        fetcher=lambda: fetch_employees(urlopen=flask_urlopen, env_path=env_file),
        env_path=env_file,
        state_path=state_file,
        cache_path=cache_file,
        queue_path=queue_file,
    )
    assert controller.has_cache is True

    # 1. Derruba o backend e passa crachás
    backend_up = False
    r1 = controller.handle_tag("TAG-ATIVA")
    r2 = controller.handle_tag("FF:EE:DD")
    r3 = controller.handle_tag("TAG-ATIVA")
    assert len(controller.pending_events) == 3
    assert admin_client.get("/api/events").get_json() == []

    # 2. Religa o backend e sincroniza a fila
    backend_up = True
    synced = controller.sync_pending_events()
    assert synced == 3
    assert controller.pending_events == []
    assert json.loads(queue_file.read_text(encoding="utf-8")) == []

    # 3. Confere os logs no backend (ordem decrescente de timestamp na listagem, todos presentes)
    logs = admin_client.get("/api/events").get_json()
    assert [e["id"] for e in logs] == [r3["event"]["id"], r2["event"]["id"], r1["event"]["id"]]
    assert [e["type"] for e in logs] == ["saida", "tentativa_invasao", "entrada"]
    assert logs[0]["employee_id"] == emp["id"]
    assert logs[1]["employee_id"] is None
    assert logs[2]["employee_id"] == emp["id"]

    # 4. Idempotência: reenvios repetidos (em lote e individual) não duplicam registros no banco
    res_batch_dup = send_events_batch(
        [r1["event"], r2["event"], r3["event"]],
        urlopen=flask_urlopen,
        env_path=env_file,
    )
    assert res_batch_dup == {"received": 3, "created": 0}
    send_event(r1["event"], urlopen=flask_urlopen, env_path=env_file)
    assert len(admin_client.get("/api/events").get_json()) == 3
