import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "study-home"
    monkeypatch.setenv("STUDY_LOOP_HOME", str(h))
    return h


@pytest.fixture
def course(tmp_path, home):
    from studylib.course import init_course
    return init_course(tmp_path / "模电", "analog-electronics", "模拟电子技术", "2026-07-25")
