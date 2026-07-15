from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import ValidationError

from .errors import DuplicateEvent, InvalidSchema
from .ioutils import append_jsonl, now_iso, read_jsonl
from .schemas import Event


def events_path(root: Path) -> Path:
    return Path(root) / ".study" / "events.jsonl"


def new_event(
    course_id: str,
    event_type: str,
    payload: dict | None = None,
    *,
    session_id: str = "session_adhoc",
    actor: str = "student",
    source: str = "main_session",
) -> dict:
    return Event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        timestamp=now_iso(),
        event_type=event_type,
        course_id=course_id,
        session_id=session_id,
        actor=actor,
        source=source,
        payload=payload or {},
    ).model_dump()


def append_event(root: Path, event: dict, *, check_duplicate: bool = False) -> dict:
    try:
        ev = Event.model_validate(event).model_dump()
    except ValidationError as e:
        raise InvalidSchema(f"invalid event: {e}") from e
    if check_duplicate:
        seen = {x["event_id"] for x in read_jsonl(events_path(root))}
        if ev["event_id"] in seen:
            raise DuplicateEvent(f"duplicate event_id: {ev['event_id']}")
    append_jsonl(events_path(root), ev)
    return ev


def read_events(root: Path) -> list[dict]:
    return read_jsonl(events_path(root))
