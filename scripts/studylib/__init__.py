"""study-loop core library. CLI scripts in scripts/ are thin wrappers around this package."""
import sys as _sys
from pathlib import Path

# Ensure the 'fsrs' pip package is found before scripts/fsrs.py.
# When a script in scripts/ runs, Python inserts scripts/ as sys.path[0].
# This causes 'from fsrs import ...' in fsrs_store.py to find scripts/fsrs.py
# instead of the installed fsrs package. Fix: move scripts/ after site-packages
# by removing it from sys.path and re-appending at the end.
_scripts_dir = str(Path(__file__).resolve().parent.parent)  # scripts/ dir (parent of this package)
while _scripts_dir in _sys.path:
    _sys.path.remove(_scripts_dir)
_sys.path.append(_scripts_dir)

SCHEMA_VERSION = "2.0"
