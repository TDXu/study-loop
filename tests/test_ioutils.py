import json
from pathlib import Path

import pytest


def test_atomic_write_and_read_json(tmp_path):
    from studylib.ioutils import atomic_write_json
    p = tmp_path / "a" / "b.json"
    atomic_write_json(p, {"x": "中文", "n": 1})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"x": "中文", "n": 1}
    assert not list(p.parent.glob("*.tmp*")), "temp file must be cleaned up"


def test_jsonl_append_and_read(tmp_path):
    from studylib.ioutils import append_jsonl, read_jsonl
    p = tmp_path / "log.jsonl"
    assert read_jsonl(p) == []
    append_jsonl(p, {"a": 1})
    append_jsonl(p, {"b": "二"})
    assert read_jsonl(p) == [{"a": 1}, {"b": "二"}]


def test_write_jsonl_atomic_rewrite(tmp_path):
    from studylib.ioutils import write_jsonl, read_jsonl
    p = tmp_path / "rows.jsonl"
    write_jsonl(p, [{"i": 0}, {"i": 1}])
    write_jsonl(p, [{"i": 2}])
    assert read_jsonl(p) == [{"i": 2}]


def test_now_iso_has_offset():
    from studylib.ioutils import now_iso
    s = now_iso()
    assert "T" in s and ("+" in s or "-" in s[10:] or s.endswith("Z"))


def test_course_lock_creates_lockfile(tmp_path):
    from studylib.ioutils import course_lock
    with course_lock(tmp_path):
        assert (tmp_path / ".study" / "locks" / "state.lock").exists()


def test_course_lock_timeout(tmp_path):
    from studylib.errors import StateLockTimeout
    from studylib.ioutils import course_lock
    outer = course_lock(tmp_path)
    outer.acquire()
    try:
        with pytest.raises(StateLockTimeout):
            with course_lock(tmp_path, timeout=0.2):
                pass
    finally:
        outer.release()
