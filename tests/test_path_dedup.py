"""Regression guard for the scripts/ -> sys.path demotion in studylib/__init__.py.

When the skill is installed via symlink, ``sys.path`` holds the *symlink* form of
``scripts/`` while ``studylib/__init__.py`` computes the *resolved* real path. The
dedup must canonicalise both sides (via realpath) or ``scripts/fsrs.py`` shadows the
``fsrs`` pip package and ``from fsrs import ...`` in fsrs_store.py triggers a
circular import. These tests do not depend on a real symlink existing on disk.
"""
from studylib import _demote_scripts_dir


def _fake_realpath(real, link):
    """A realpath() that canonicalises both *real* and *link* to *real*."""

    def _rp(p):
        return real if p in (real, link) else p

    return _rp


def test_demote_handles_symlink_form_on_path():
    # sys.path holds the symlink form; __init__ computes the resolved real path.
    real = "/repo/study-loop/scripts"
    link = "/skills/study-loop/scripts"  # symlink -> real
    site = "/venv/Lib/site-packages"

    sys_path = [link, site]  # symlink form at the front, like a real CLI run
    _demote_scripts_dir(sys_path, real, realpath=_fake_realpath(real, link))

    assert link not in sys_path, "symlink-form entry must be deduped via realpath"
    assert sys_path[-1] == real, "scripts dir must be demoted to the end"
    assert sys_path[0] == site, "site-packages must now come before scripts/"


def test_demote_removes_both_forms_and_keeps_one():
    real = "/repo/study-loop/scripts"
    link = "/skills/study-loop/scripts"
    sys_path = [link, real]  # both forms present
    _demote_scripts_dir(sys_path, real, realpath=_fake_realpath(real, link))

    assert sys_path == [real], "both forms removed, real form appended exactly once"


def test_demote_keeps_unrelated_entries():
    site = "/venv/Lib/site-packages"
    scripts = "/repo/study-loop/scripts"
    sys_path = [scripts, site, "/other"]
    _demote_scripts_dir(sys_path, scripts)  # default realpath

    assert sys_path == [site, "/other", scripts]


def test_demote_is_idempotent():
    scripts = "/repo/study-loop/scripts"
    sys_path = [scripts]
    _demote_scripts_dir(sys_path, scripts)
    _demote_scripts_dir(sys_path, scripts)

    assert sys_path.count(scripts) == 1
