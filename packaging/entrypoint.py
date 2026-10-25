"""Frozen entry point for the M29 Windows companion (PyInstaller)."""

from __future__ import annotations

import sys

from skill_gap_agent.desktop import main

if __name__ == "__main__":
    sys.exit(main())
