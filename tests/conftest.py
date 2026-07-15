import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "study-home"
    monkeypatch.setenv("STUDY_LOOP_HOME", str(h))
    return h
