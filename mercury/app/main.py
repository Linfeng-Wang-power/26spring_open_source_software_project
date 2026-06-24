"""Mercury PySide6 entry point.

Run::

    python -m mercury
    # or, for the legacy script-style invocation kept for the bundle:
    python run_lumen.py

This is a thin wrapper over ``mercury.gui.main`` so the GUI module itself
does not need to know about the binary entry. PyInstaller targets this
file via ``run_lumen.py`` at the repo root.
"""

from __future__ import annotations

from mercury.gui import main

__all__ = ["main"]
