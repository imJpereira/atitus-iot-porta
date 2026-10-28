import logging

from rasp.rfid import (
    DEFAULT_DEBOUNCE_SECONDS,
    get_debounce_seconds,
    normalize_uid,
    read_once,
    run_reader_loop,
)


class FakeClock:
    def __init__(self, initial: float = 100.0):
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SequenceReader:
    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def read_no_block(self):
        self.calls += 1
        if not self.items:
            return None, ""
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, ""


def test_normalize_uid_matches_backend_format():
    assert normalize_uid("  aa:bb:cc  ") == "AA:BB:CC"
    assert normalize_uid(123456) == "123456"
    assert normalize_uid("   ") is None
    assert normalize_uid(None) is None


def test_get_debounce_seconds_default_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("RFID_DEBOUNCE_SECONDS", raising=False)
    assert get_debounce_seconds(tmp_path / "missing.env") == DEFAULT_DEBOUNCE_SECONDS

    env_file = tmp_path / ".env"
    env_file.write_text("RFID_DEBOUNCE_SECONDS=4.5\n", encoding="utf-8")
    assert get_debounce_seconds(env_file) == 4.5

    monkeypatch.setenv("RFID_DEBOUNCE_SECONDS", "2")
    assert get_debounce_seconds(env_file) == 2.0


def test_same_tag_within_debounce_is_ignored_and_accepted_after():
    clock = FakeClock()
    last_seen: dict[str, float] = {}
    delivered: list[str] = []
    reader = SequenceReader([" abcd ", "abcd", "ABCD", "abcd"])

    assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) == "ABCD"
    clock.advance(1.0)
    assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) is None
    clock.advance(1.9)
    assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) is None
    clock.advance(0.1)
    assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) == "ABCD"

    assert delivered == ["ABCD", "ABCD"]


def test_different_tag_during_debounce_is_processed_normally():
    clock = FakeClock()
    last_seen: dict[str, float] = {}
    delivered: list[str] = []
    reader = SequenceReader(["tag-1", "tag-2", "tag-1"])

    assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) == "TAG-1"
    clock.advance(0.5)
    assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) == "TAG-2"
    clock.advance(0.5)
    assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) is None

    assert delivered == ["TAG-1", "TAG-2"]


def test_no_tag_present_generates_no_event():
    clock = FakeClock()
    last_seen: dict[str, float] = {}
    delivered: list[str] = []
    reader = SequenceReader([None, "   ", None])

    for _ in range(3):
        assert read_once(reader, last_seen, 3.0, on_tag=delivered.append, clock=clock) is None

    assert delivered == []
    assert last_seen == {}


def test_reader_error_is_logged_and_loop_continues(caplog):
    clock = FakeClock()
    delivered: list[str] = []
    reader = SequenceReader(
        [
            "tag-a",
            RuntimeError("SPI disconnected"),
            None,
            "tag-a",
            "tag-b",
        ]
    )

    with caplog.at_level(logging.ERROR):
        run_reader_loop(
            delivered.append,
            reader=reader,
            debounce_seconds=3.0,
            poll_interval=0,
            clock=clock,
            max_iterations=5,
        )

    assert delivered == ["TAG-A", "TAG-B"]
    assert "Erro ao ler o leitor RFID" in caplog.text
