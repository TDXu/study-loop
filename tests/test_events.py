import pytest


def test_new_event_shape(tmp_path):
    from studylib.events import new_event
    ev = new_event("c1", "kc_created", {"kc_id": "k1", "name": "K"})
    assert ev["event_id"].startswith("evt_") and len(ev["event_id"]) == 16
    assert ev["schema_version"] == "2.0"
    assert ev["event_type"] == "kc_created"
    assert ev["payload"]["kc_id"] == "k1"


def test_append_and_read(tmp_path):
    from studylib.events import append_event, new_event, read_events
    e1 = append_event(tmp_path, new_event("c1", "course_initialized", {}))
    e2 = append_event(tmp_path, new_event("c1", "kc_created", {"kc_id": "k1"}))
    evs = read_events(tmp_path)
    assert [e["event_id"] for e in evs] == [e1["event_id"], e2["event_id"]]


def test_duplicate_event_rejected(tmp_path):
    from studylib.errors import DuplicateEvent
    from studylib.events import append_event, new_event
    ev = new_event("c1", "course_initialized", {})
    append_event(tmp_path, ev)
    with pytest.raises(DuplicateEvent):
        append_event(tmp_path, ev, check_duplicate=True)


def test_append_rejects_bad_event(tmp_path):
    from studylib.errors import InvalidSchema
    from studylib.events import append_event
    with pytest.raises(InvalidSchema):
        append_event(tmp_path, {"event_type": "nope"})
