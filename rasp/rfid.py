import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from rasp.test_hardware import ROOT, load_env

logger = logging.getLogger(__name__)

DEFAULT_DEBOUNCE_SECONDS = 3.0


def normalize_uid(raw: object) -> str | None:
    if raw is None:
        return None
    tag = str(raw).strip().upper()
    return tag or None


def get_debounce_seconds(env_path: Path = ROOT / ".env") -> float:
    load_env(env_path)
    return float(os.environ.get("RFID_DEBOUNCE_SECONDS", DEFAULT_DEBOUNCE_SECONDS))


def read_uid(reader) -> str | None:
    read_fn = getattr(reader, "read_no_block", None) or reader.read
    raw, *_ = read_fn()
    return normalize_uid(raw)


def read_once(
    reader,
    last_seen: dict[str, float],
    debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    on_tag: Callable[[str], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> str | None:
    try:
        tag = read_uid(reader)
    except Exception:
        logger.exception("Erro ao ler o leitor RFID")
        return None

    if tag is None:
        return None

    now = clock()
    if tag in last_seen and (now - last_seen[tag]) < debounce_seconds:
        return None

    last_seen[tag] = now
    if on_tag is not None:
        on_tag(tag)
    return tag


def run_reader_loop(
    on_tag: Callable[[str], None],
    *,
    reader=None,
    debounce_seconds: float | None = None,
    poll_interval: float = 0.05,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    stop_event=None,
    max_iterations: int | None = None,
    env_path: Path = ROOT / ".env",
) -> None:
    if debounce_seconds is None:
        debounce_seconds = get_debounce_seconds(env_path)
    if reader is None:
        from mfrc522 import SimpleMFRC522  # type: ignore[import-not-found]

        reader = SimpleMFRC522()

    last_seen: dict[str, float] = {}
    iterations = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        if max_iterations is not None and iterations >= max_iterations:
            break
        read_once(reader, last_seen, debounce_seconds, on_tag=on_tag, clock=clock)
        iterations += 1
        if poll_interval > 0:
            sleep(poll_interval)
