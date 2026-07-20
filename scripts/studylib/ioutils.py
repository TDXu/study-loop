from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout

from .errors import StateLockTimeout


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    atomic_write_text(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def append_jsonl(path: Path, obj: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class _CourseLock:
    """Non-reentrant course-level lock; raises StateLockTimeout on timeout."""

    def __init__(self, course_root: Path, timeout: float):
        lock_dir = Path(course_root) / ".study" / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(lock_dir / "state.lock"), thread_local=False)
        self._timeout = timeout

    def acquire(self):
        try:
            self._lock.acquire(timeout=self._timeout)
        except Timeout as e:
            raise StateLockTimeout(
                f"course is locked by another study-loop process: {self._lock.lock_file}"
            ) from e

    def release(self):
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def course_lock(course_root: Path, timeout: float = 10.0) -> _CourseLock:
    return _CourseLock(course_root, timeout)
