from collections.abc import Callable
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
import urllib.request
from uuid import uuid4
from zoneinfo import ZoneInfo

from rasp.rfid import normalize_uid, run_reader_loop
from rasp.test_hardware import ROOT, get_pins, load_env

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_API_BASE_URL = "http://127.0.0.1:5000"
SOURCE = "raspberry_pi"
DEFAULT_STATE_PATH = ROOT / "data" / "rasp_state.json"

PATTERNS: dict[str, tuple[tuple[tuple[str, ...], float, float], ...]] = {
    "first_entry": (
        (("GPIO_LED_GREEN", "GPIO_BUZZER"), 0.2, 0.05),
    ),
    "return_entry": (
        (("GPIO_LED_GREEN", "GPIO_BUZZER"), 0.1, 0.08),
        (("GPIO_LED_GREEN", "GPIO_BUZZER"), 0.1, 0.05),
    ),
    "access_denied": (
        (("GPIO_LED_YELLOW", "GPIO_BUZZER"), 0.25, 0.1),
        (("GPIO_LED_YELLOW", "GPIO_BUZZER"), 0.25, 0.05),
    ),
    "intrusion": (
        (("GPIO_LED_RED", "GPIO_BUZZER"), 0.15, 0.08),
        (("GPIO_LED_RED", "GPIO_BUZZER"), 0.15, 0.08),
        (("GPIO_LED_RED", "GPIO_BUZZER"), 0.15, 0.05),
    ),
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def local_date(moment: datetime) -> str:
    return moment.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


def index_employees(employees: list[dict]) -> dict[str, dict]:
    by_tag: dict[str, dict] = {}
    for emp in employees:
        tag = normalize_uid(emp.get("rfid_tag"))
        if tag:
            by_tag[tag] = emp
    return by_tag


def classify_access(
    tag: str,
    employees_by_tag: dict[str, dict],
    entered_today: set[str],
    inside: set[str] | None = None,
) -> tuple[str, str, str]:
    employee = employees_by_tag.get(tag)
    if employee is None:
        return "intrusion", "tentativa_invasao", f"Alerta de invasão: tag não cadastrada ({tag})"

    name = employee["name"]
    if not employee.get("is_active") or not employee.get("has_room_access"):
        return "access_denied", "acesso_negado", f"Acesso negado, {name}"

    if inside is not None:
        if tag in inside:
            inside.remove(tag)
            return "return_entry", "saida", f"Até logo, {name}"
        inside.add(tag)

    if tag not in entered_today:
        entered_today.add(tag)
        return "first_entry", "entrada", f"Bem-vindo, {name}"

    return "return_entry", "entrada", f"Bem-vindo de volta, {name}"


def build_event(
    tag: str,
    event_type: str,
    moment: datetime,
    *,
    event_id: str | None = None,
    source: str = SOURCE,
) -> dict[str, str]:
    return {
        "id": event_id or str(uuid4()),
        "rfid_tag": tag,
        "timestamp": moment.astimezone(timezone.utc).strftime(UTC_FORMAT),
        "type": event_type,
        "source": source,
    }


def emit_feedback(
    case: str,
    *,
    gpio=None,
    pins: dict[str, int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    env_path: Path = ROOT / ".env",
) -> None:
    if pins is None:
        pins = get_pins(env_path)
    if gpio is None:
        import RPi.GPIO as gpio  # type: ignore[import-not-found]

    output_pins = (
        pins["GPIO_LED_GREEN"],
        pins["GPIO_LED_YELLOW"],
        pins["GPIO_LED_RED"],
        pins["GPIO_BUZZER"],
    )
    gpio.setwarnings(False)
    gpio.setmode(gpio.BCM)
    for pin in output_pins:
        gpio.setup(pin, gpio.OUT, initial=gpio.LOW)

    for pin_keys, on_seconds, off_seconds in PATTERNS[case]:
        for key in pin_keys:
            gpio.output(pins[key], gpio.HIGH)
        sleep(on_seconds)
        for key in pin_keys:
            gpio.output(pins[key], gpio.LOW)
        sleep(off_seconds)


def fetch_employees(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    urlopen: Callable = urllib.request.urlopen,
    env_path: Path = ROOT / ".env",
) -> list[dict]:
    load_env(env_path)
    url = (base_url or os.environ.get("API_BASE_URL") or DEFAULT_API_BASE_URL).rstrip("/")
    key = api_key if api_key is not None else os.environ.get("PI_API_KEY", "")
    req = urllib.request.Request(f"{url}/api/sync/employees", headers={"X-API-Key": key})
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_event(
    event: dict[str, str],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    urlopen: Callable = urllib.request.urlopen,
    env_path: Path = ROOT / ".env",
) -> dict:
    load_env(env_path)
    url = (base_url or os.environ.get("API_BASE_URL") or DEFAULT_API_BASE_URL).rstrip("/")
    key = api_key if api_key is not None else os.environ.get("PI_API_KEY", "")
    data = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/events",
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


class AccessController:
    def __init__(
        self,
        employees: list[dict] | None = None,
        *,
        gpio=None,
        pins: dict[str, int] | None = None,
        clock: Callable[[], datetime] = now_utc,
        sleep: Callable[[float], None] = time.sleep,
        display: Callable[[str], None] = print,
        sender: Callable[[dict[str, str]], object] | None = None,
        env_path: Path = ROOT / ".env",
        state_path: Path | None = DEFAULT_STATE_PATH,
    ) -> None:
        self.env_path = env_path
        self.state_path = state_path
        self.pins = pins if pins is not None else get_pins(env_path)
        self.gpio = gpio
        self.clock = clock
        self.sleep = sleep
        self.display = display
        self.sender = sender or (lambda ev: send_event(ev, env_path=env_path))
        self.employees_by_tag = index_employees(employees or [])
        self.current_date: str | None = None
        self.entered_today: set[str] = set()
        self.inside: set[str] = set()
        self._load_state()

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.is_file():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Arquivo de estado inválido em %s; iniciando limpo", self.state_path)
            return
        if isinstance(data, dict) and isinstance(data.get("date"), str):
            self.current_date = data["date"]
            self.entered_today = {t for raw in data.get("entered_today", []) if (t := normalize_uid(raw))}
            self.inside = {t for raw in data.get("inside", []) if (t := normalize_uid(raw))}

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": self.current_date,
            "entered_today": sorted(self.entered_today),
            "inside": sorted(self.inside),
        }
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")

    def update_employees(self, employees: list[dict]) -> None:
        self.employees_by_tag = index_employees(employees)

    def handle_tag(self, raw_tag: object) -> dict | None:
        tag = normalize_uid(raw_tag)
        if tag is None:
            return None

        moment = self.clock()
        day = local_date(moment)
        if day != self.current_date:
            self.current_date = day
            self.entered_today.clear()
            self.inside.clear()

        case, event_type, message = classify_access(
            tag, self.employees_by_tag, self.entered_today, self.inside
        )
        self._save_state()
        self.display(message)
        emit_feedback(case, gpio=self.gpio, pins=self.pins, sleep=self.sleep, env_path=self.env_path)
        event = build_event(tag, event_type, moment)
        try:
            self.sender(event)
        except Exception:
            logger.exception("Erro ao enviar evento de acesso ao backend")
        return {"case": case, "message": message, "event": event}


def run_access_loop(*, controller: AccessController | None = None, env_path: Path = ROOT / ".env", **loop_kwargs) -> None:
    if controller is None:
        employees = fetch_employees(env_path=env_path)
        controller = AccessController(employees, env_path=env_path)
    run_reader_loop(controller.handle_tag, env_path=env_path, **loop_kwargs)
