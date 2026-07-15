from __future__ import annotations

import os
from pathlib import Path

from .errors import CourseNotFound


def study_home() -> Path:
    return Path(os.environ.get("STUDY_LOOP_HOME", str(Path.home() / ".study-loop")))


def find_course_root(start: Path | None = None) -> Path:
    p = Path(start or Path.cwd()).resolve()
    for cand in (p, *p.parents):
        if (cand / "course.yaml").is_file():
            return cand
    raise CourseNotFound(
        f"course.yaml not found from {p}. cd into a course workspace or run init_course.py first."
    )


def study_dir(root: Path) -> Path:
    return Path(root) / ".study"
