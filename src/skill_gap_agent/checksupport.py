"""Shared isolation for the offline checks.

Every check that exercises the pipeline must redirect the artifact store at a
scratch directory. Without this the check writes its stub fixtures into the
user's live workspace: the flat store has one location, so a check run would
overwrite real gaps/plan/profile and leave fixture JDs behind (the old
per-SHA layout hid this by accident — checks and real runs happened to use
different folders).

`isolated_store()` sets `SKILL_GAP_DATA_DIR` for its duration and restores the
previous value on exit, so a check never touches real data even if it fails.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path

from .store import DATA_DIR_ENV


@contextlib.contextmanager
def isolated_store(prefix: str = "sg-check-"):
    """Redirect the artifact store to a throwaway directory."""
    previous = os.environ.get(DATA_DIR_ENV)
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    os.environ[DATA_DIR_ENV] = str(tmp)
    try:
        yield tmp
    finally:
        if previous is None:
            os.environ.pop(DATA_DIR_ENV, None)
        else:
            os.environ[DATA_DIR_ENV] = previous
        shutil.rmtree(tmp, ignore_errors=True)
