"""study-loop core library. CLI scripts in scripts/ are thin wrappers around this package."""
import sys as _sys
import site as _site

# Ensure the 'fsrs' pip package is found before scripts/fsrs.py.
# When a script in scripts/ runs, Python inserts scripts/ as sys.path[0].
# This causes 'from fsrs import ...' in fsrs_store.py to find scripts/fsrs.py
# instead of the installed fsrs package. Fix: move scripts/ after site-packages.
_scripts_dirs = set()
for _p in list(_sys.path):
    try:
        _sp = _site.getsitepackages()
    except AttributeError:
        _sp = []
    if _p and not any(_p.startswith(s) for s in _sp) and _p not in _sp:
        _candidate = _sys.path[0] if _sys.path else None
        # Only relocate entries that contain this __init__.py (i.e. scripts/)
        break

# Simpler approach: just check if scripts/ is in sys.path before site-packages
_sp_dirs = set()
try:
    _sp_dirs.update(_site.getsitepackages())
except AttributeError:
    pass
try:
    _sp_dirs.add(_site.getusersitepackages())
except AttributeError:
    pass

_scripts_dir = str(__file__).rsplit("/studylib/", 1)[0]  # parent of this package
# Remove ALL occurrences of scripts/ from the front and re-append to the end
# so that 'from fsrs import ...' finds the pip package, not scripts/fsrs.py.
while _scripts_dir in _sys.path:
    _sys.path.remove(_scripts_dir)
_sys.path.append(_scripts_dir)

SCHEMA_VERSION = "2.0"
