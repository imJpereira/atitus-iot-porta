from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def day_bounds(date: str) -> tuple[str, str]:
    """'YYYY-MM-DD' -> (start, end) of that local day as UTC 'YYYY-MM-DDTHH:MM:SSZ'. ValueError if invalid."""
    day = datetime.strptime(date, "%Y-%m-%d")
    if day.strftime("%Y-%m-%d") != date:
        raise ValueError(date)
    start = day.replace(tzinfo=LOCAL_TZ)
    end = (day + timedelta(days=1)).replace(tzinfo=LOCAL_TZ)
    return tuple(m.astimezone(timezone.utc).strftime(UTC_FORMAT) for m in (start, end))


def pair_sessions(events: list[tuple[str, str]]) -> list[dict]:
    """Pair ordered (type, utc timestamp) entrada/saida events into sessions.

    saida without an open entrada is dropped; an entrada never closed is kept with sem_saida.
    """
    sessions, opened = [], None
    for kind, moment in events:
        if kind == "entrada":
            if opened:
                sessions.append(open_session(opened))
            opened = moment
        elif opened:
            seconds = int((parse(moment) - parse(opened)).total_seconds())
            sessions.append(
                {"entrada": opened, "saida": moment, "duration_seconds": seconds, "sem_saida": False}
            )
            opened = None
    if opened:
        sessions.append(open_session(opened))
    return sessions


def open_session(entrada: str) -> dict:
    return {"entrada": entrada, "saida": None, "duration_seconds": None, "sem_saida": True}


def parse(moment: str) -> datetime:
    return datetime.strptime(moment, UTC_FORMAT)
