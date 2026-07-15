from __future__ import annotations

import json
from pathlib import Path

import yaml

from .errors import InvalidWorkspace
from .events import append_event, new_event
from .ioutils import atomic_write_json, atomic_write_text, now_iso
from .paths import study_home
from .schemas import SCHEMA_VERSION

DEFAULT_PROFILE = {
    "quantitative": 0.3, "conceptual": 0.3, "procedural": 0.2,
    "programming": 0.0, "language": 0.0, "memory": 0.2,
    "confidence": 0.3,
}

WORKSPACE_DIRS = [
    "materials/syllabus", "materials/textbook", "materials/slides",
    "materials/homework", "materials/past-exams", "materials/notes",
    "notes", "output", ".study/locks", ".study/cache",
]


def init_course(path: Path, course_id: str, name: str, exam_date: str | None = None) -> Path:
    root = Path(path)
    if (root / "course.yaml").exists():
        raise InvalidWorkspace(f"course.yaml already exists in {root}")
    for d in WORKSPACE_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "id": course_id,
        "name": name,
        "exam_date": exam_date,
        "created_at": now_iso(),
        "profile": dict(DEFAULT_PROFILE),
    }
    atomic_write_text(root / "course.yaml", yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    append_event(root, new_event(course_id, "course_initialized", {"name": name, "exam_date": exam_date}))
    register_course_globally(course_id, root)
    return root


def load_course(root: Path) -> dict:
    return yaml.safe_load((Path(root) / "course.yaml").read_text(encoding="utf-8"))


def register_course_globally(course_id: str, root: Path) -> None:
    home = study_home()
    home.mkdir(parents=True, exist_ok=True)
    reg_path = home / "registry.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    else:
        reg = {"schema_version": SCHEMA_VERSION, "courses": {}}
    reg["courses"][course_id] = {"path": str(Path(root)), "registered_at": now_iso()}
    atomic_write_json(reg_path, reg)
