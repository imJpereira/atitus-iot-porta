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
DEFAULT_CACHE_PATH = ROOT / "data" / "employees_cache.json"
DEFAULT_QUEUE_PATH = ROOT / "data" / "events_queue.json"
DEFAULT_SYNC_INTERVAL_SECONDS = 60.0
DEFAULT_QUEUE_MAX_SIZE = 1000

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


def get_sync_interval(env_path: Path = ROOT / ".env") -> float:
    load_env(env_path)
    return float(os.environ.get("CACHE_SYNC_INTERVAL_SECONDS", DEFAULT_SYNC_INTERVAL_SECONDS))


def get_queue_max_size(env_path: Path = ROOT / ".env") -> int:
    load_env(env_path)
    return int(os.environ.get("EVENT_QUEUE_MAX_SIZE", DEFAULT_QUEUE_MAX_SIZE))


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
        fetcher: Callable[[], list[dict]] | None = None,
        sync_interval: float | None = None,
        queue_max_size: int | None = None,
        env_path: Path = ROOT / ".env",
        state_path: Path | None = DEFAULT_STATE_PATH,
        cache_path: Path | None = DEFAULT_CACHE_PATH,
        queue_path: Path | None = DEFAULT_QUEUE_PATH,
    ) -> None:
        self.env_path = env_path
        self.state_path = state_path
        self.cache_path = cache_path
        self.queue_path = queue_path
        self.pins = pins if pins is not None else get_pins(env_path)
        self.gpio = gpio
        self.clock = clock
        self.sleep = sleep
        self.display = display
        self.sender = sender or (lambda ev: send_event(ev, env_path=env_path))
        self.sync_interval = sync_interval if sync_interval is not None else get_sync_interval(env_path)
        self.queue_max_size = queue_max_size if queue_max_size is not None else get_queue_max_size(env_path)
        self.updated_at: str | None = None
        self.last_sync_at: datetime | None = None
        self.current_date: str | None = None
        self.entered_today: set[str] = set()
        self.inside: set[str] = set()
        self.pending_events: list[dict[str, str]] = []
        self._load_state()
        self._load_queue()

        if employees is not None:
            self.fetcher = fetcher
            self.employees_by_tag = index_employees(employees)
            self.has_cache = True
        else:
            self.fetcher = fetcher or (lambda: fetch_employees(env_path=env_path))
            self.employees_by_tag = {}
            self.has_cache = False
            self._load_cache()
            self.sync_employees()

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

    def _load_cache(self) -> None:
        if self.cache_path is None or not self.cache_path.is_file():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Arquivo de cache inválido em %s; ignorando", self.cache_path)
            return
        if isinstance(data, dict) and isinstance(data.get("employees"), list):
            self.employees_by_tag = index_employees(data["employees"])
            self.updated_at = data.get("updated_at") if isinstance(data.get("updated_at"), str) else None
            self.has_cache = True
            logger.info("Cache local de colaboradores carregado de %s (updated_at=%s)", self.cache_path, self.updated_at)

    def _save_cache(self, employees: list[dict]) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"updated_at": self.updated_at, "employees": employees}
        self.cache_path.write_text(json.dumps(payload), encoding="utf-8")

    def _load_queue(self) -> None:
        if self.queue_path is None or not self.queue_path.is_file():
            return
        try:
            data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Arquivo de fila inválido em %s; iniciando vazio", self.queue_path)
            return
        if isinstance(data, list):
            self.pending_events = [ev for ev in data if isinstance(ev, dict)]

    def _save_queue(self) -> None:
        if self.queue_path is None:
            return
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.queue_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.pending_events, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.queue_path)

    def _enqueue_event(self, event: dict[str, str]) -> None:
        self.pending_events.append(event)
        self._save_queue()
        if len(self.pending_events) >= self.queue_max_size:
            logger.warning(
                "Fila local de eventos atingiu %d itens (limite configurado: %d); nenhum evento foi descartado",
                len(self.pending_events),
                self.queue_max_size,
            )

    def update_employees(self, employees: list[dict]) -> None:
        self.employees_by_tag = index_employees(employees)
        self.has_cache = True

    def sync_employees(self, moment: datetime | None = None) -> bool:
        if self.fetcher is None:
            return self.has_cache
        now = moment or self.clock()
        self.last_sync_at = now
        try:
            employees = self.fetcher()
        except Exception:
            if self.has_cache:
                logger.warning(
                    "Falha ao atualizar cache de colaboradores; mantendo cache anterior (%s)",
                    self.updated_at,
                )
            else:
                logger.error("Sem conexão com o backend e sem cache local de colaboradores disponível")
            return False
        self.update_employees(employees)
        self.updated_at = now.astimezone(timezone.utc).strftime(UTC_FORMAT)
        self._save_cache(employees)
        return True

    def maybe_sync(self, moment: datetime | None = None) -> bool:
        if self.fetcher is None:
            return self.has_cache
        now = moment or self.clock()
        if (
            not self.has_cache
            or self.last_sync_at is None
            or (now - self.last_sync_at).total_seconds() >= self.sync_interval
        ):
            return self.sync_employees(now)
        return self.has_cache

    def handle_tag(self, raw_tag: object) -> dict | None:
        tag = normalize_uid(raw_tag)
        if tag is None:
            return None

        moment = self.clock()
        self.maybe_sync(moment)
        day = local_date(moment)
        if day != self.current_date:
            self.current_date = day
            self.entered_today.clear()
            self.inside.clear()

        if not self.has_cache:
            logger.warning("Tag %s não validável: sem conexão e sem cache local de colaboradores", tag)
            case, event_type, message = (
                "access_denied",
                "acesso_negado",
                f"Acesso negado: cache local indisponível ({tag})",
            )
        else:
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
            logger.warning("Sem conexão com o backend; evento %s salvo na fila local", event["id"])
            self._enqueue_event(event)
        return {"case": case, "message": message, "event": event}


def run_access_loop(*, controller: AccessController | None = None, env_path: Path = ROOT / ".env", **loop_kwargs) -> None:
    if controller is None:
        controller = AccessController(env_path=env_path)
    run_reader_loop(controller.handle_tag, on_tick=controller.maybe_sync, env_path=env_path, **loop_kwargs)
