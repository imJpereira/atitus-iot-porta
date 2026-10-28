from rasp.test_hardware import DEFAULT_PINS, get_pins, run_hardware_test


class FakeGPIO:
    BCM = "BCM"
    OUT = "OUT"
    LOW = 0
    HIGH = 1

    def __init__(self):
        self.events = []

    def setwarnings(self, flag):
        self.events.append(("setwarnings", flag))

    def setmode(self, mode):
        self.events.append(("setmode", mode))

    def setup(self, pin, direction, initial=0):
        self.events.append(("setup", pin, direction, initial))

    def output(self, pin, value):
        self.events.append(("output", pin, value))

    def cleanup(self):
        self.events.append(("cleanup",))


class FakeReader:
    def __init__(self, uid=" 1234ab "):
        self.uid = uid

    def read(self):
        return self.uid, ""


def test_get_pins_defaults(monkeypatch, tmp_path):
    for key in DEFAULT_PINS:
        monkeypatch.delenv(key, raising=False)
    pins = get_pins(tmp_path / "missing.env")
    assert pins == {
        "GPIO_LED_GREEN": 12,
        "GPIO_LED_YELLOW": 16,
        "GPIO_LED_RED": 21,
        "GPIO_BUZZER": 14,
        "GPIO_RFID_RST": 25,
        "GPIO_RFID_SDA": 8,
    }


def test_get_pins_from_dotenv_and_env_override(monkeypatch, tmp_path):
    for key in DEFAULT_PINS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GPIO_LED_GREEN=17\nGPIO_BUZZER=18\n", encoding="utf-8")
    monkeypatch.setenv("GPIO_LED_RED", "22")

    pins = get_pins(env_file)
    assert pins["GPIO_LED_GREEN"] == 17
    assert pins["GPIO_BUZZER"] == 18
    assert pins["GPIO_LED_RED"] == 22
    assert pins["GPIO_LED_YELLOW"] == 16


def test_run_hardware_test_pulses_each_component_and_reads_uid(monkeypatch, tmp_path):
    for key in DEFAULT_PINS:
        monkeypatch.delenv(key, raising=False)
    gpio = FakeGPIO()
    reader = FakeReader(" 998877aabb ")

    uid = run_hardware_test(gpio=gpio, reader=reader, delay=0, env_path=tmp_path / "no.env")

    assert uid == "998877AABB"
    outputs = [(pin, val) for kind, pin, val, *_ in [e + (None,) for e in gpio.events if e[0] == "output"]]
    assert outputs == [
        (12, 1),
        (12, 0),
        (16, 1),
        (16, 0),
        (21, 1),
        (21, 0),
        (14, 1),
        (14, 0),
    ]
    assert gpio.events[-1] == ("cleanup",)
