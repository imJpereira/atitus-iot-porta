import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PINS = {
    "GPIO_LED_GREEN": 12,
    "GPIO_LED_YELLOW": 16,
    "GPIO_LED_RED": 21,
    "GPIO_BUZZER": 14,
    "GPIO_RFID_RST": 25,
    "GPIO_RFID_SDA": 8,
}


def load_env(env_path: Path = ROOT / ".env") -> None:
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_pins(env_path: Path = ROOT / ".env") -> dict[str, int]:
    load_env(env_path)
    return {key: int(os.environ.get(key, default)) for key, default in DEFAULT_PINS.items()}


def pulse(gpio, pin: int, label: str, delay: float) -> None:
    print(f"[TESTE] Acionando {label} (GPIO {pin})...")
    gpio.output(pin, gpio.HIGH)
    time.sleep(delay)
    gpio.output(pin, gpio.LOW)
    time.sleep(0.1)


def run_hardware_test(gpio=None, reader=None, delay: float = 0.5, env_path: Path = ROOT / ".env") -> str:
    pins = get_pins(env_path)
    if gpio is None:
        import RPi.GPIO as gpio  # type: ignore[import-not-found]
    if reader is None:
        from mfrc522 import SimpleMFRC522  # type: ignore[import-not-found]

        reader = SimpleMFRC522()

    output_pins = (
        (pins["GPIO_LED_GREEN"], "LED Verde"),
        (pins["GPIO_LED_YELLOW"], "LED Amarelo"),
        (pins["GPIO_LED_RED"], "LED Vermelho"),
        (pins["GPIO_BUZZER"], "Buzzer"),
    )

    gpio.setwarnings(False)
    gpio.setmode(gpio.BCM)
    for pin, _ in output_pins:
        gpio.setup(pin, gpio.OUT, initial=gpio.LOW)

    try:
        for pin, label in output_pins:
            pulse(gpio, pin, label, delay)

        print("[TESTE] Aproxime uma tag RFID do leitor...")
        uid, _ = reader.read()
        tag = str(uid).strip().upper()
        print(f"UID lido: {tag}")
        return tag
    finally:
        gpio.cleanup()


if __name__ == "__main__":
    run_hardware_test()
