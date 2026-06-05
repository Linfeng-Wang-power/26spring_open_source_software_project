"""Top-level launcher for PyInstaller.

PyInstaller's --windowed app bundle wants a plain script entry rather than
``python -m mercury``. This file just delegates so the bundle and the
``python -m mercury`` form share one implementation.
"""

from mercury.app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
