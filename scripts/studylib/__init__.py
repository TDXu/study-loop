"""study-loop core library. CLI scripts in scripts/ are thin wrappers around this package."""
import os as _os
import sys as _sys
from pathlib import Path


def _demote_scripts_dir(sys_path, scripts_dir, *, realpath=_os.path.realpath):
    """Move *scripts_dir* to the end of *sys_path* so site-packages wins.

    ``studylib.fsrs_store`` does ``from fsrs import Card, Rating, Scheduler`` and
    there is a same-named ``scripts/fsrs.py`` CLI. When a script in ``scripts/``
    runs, Python inserts that dir as ``sys.path[0]`` and shadows the ``fsrs`` pip
    package, causing a circular import. Demoting it behind site-packages fixes that.

    Entries are compared via *realpath* so the dedup still works when the skill is
    installed through a symlink (e.g. ``~/.claude/skills/study-loop -> repo/study-loop``):
    ``sys.path`` then holds the symlink form while ``Path(__file__).resolve()``
    follows it, and a plain string compare would miss the entry and leave
    ``scripts/`` at the front. See ``tests/test_path_dedup.py``.
    """
    real = realpath(scripts_dir)
    sys_path[:] = [p for p in sys_path if realpath(p) != real]
    sys_path.append(scripts_dir)
    return sys_path


# scripts/ dir = parent of this package (scripts/studylib/__init__.py -> scripts/).
_scripts_dir = str(Path(__file__).resolve().parent.parent)
_demote_scripts_dir(_sys.path, _scripts_dir)

SCHEMA_VERSION = "2.0"
