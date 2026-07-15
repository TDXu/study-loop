import json

import pytest
import yaml


def test_init_course_scaffold(tmp_path, home):
    from studylib.course import init_course
    root = init_course(tmp_path / "模电", "analog-electronics", "模拟电子技术", "2026-07-25")
    for d in [
        "materials/syllabus", "materials/textbook", "materials/slides",
        "materials/homework", "materials/past-exams", "materials/notes",
        "notes", "output", ".study/locks", ".study/cache",
    ]:
        assert (root / d).is_dir(), d
    cy = yaml.safe_load((root / "course.yaml").read_text(encoding="utf-8"))
    assert cy["id"] == "analog-electronics"
    assert cy["name"] == "模拟电子技术"
    assert cy["exam_date"] == "2026-07-25"
    assert cy["schema_version"] == "2.0"
    assert set(cy["profile"]) == {
        "quantitative", "conceptual", "procedural", "programming",
        "language", "memory", "confidence",
    }


def test_init_writes_event_and_registry(tmp_path, home):
    from studylib.course import init_course
    from studylib.events import read_events
    root = init_course(tmp_path / "c", "c1", "课程一", None)
    evs = read_events(root)
    assert evs[0]["event_type"] == "course_initialized"
    reg = json.loads((home / "registry.json").read_text(encoding="utf-8"))
    assert reg["courses"]["c1"]["path"] == str(root)


def test_init_refuses_existing_workspace(tmp_path, home):
    from studylib.course import init_course
    from studylib.errors import InvalidWorkspace
    init_course(tmp_path / "c", "c1", "课程一", None)
    with pytest.raises(InvalidWorkspace):
        init_course(tmp_path / "c", "c1", "课程一", None)


def test_find_course_root(tmp_path, home):
    from studylib.course import init_course
    from studylib.errors import CourseNotFound
    from studylib.paths import find_course_root
    root = init_course(tmp_path / "c", "c1", "课程一", None)
    sub = root / "materials" / "slides"
    assert find_course_root(sub) == root
    with pytest.raises(CourseNotFound):
        find_course_root(tmp_path / "elsewhere")
