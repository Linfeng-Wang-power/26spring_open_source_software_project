"""Allow running the app via ``python -m mercury``."""

from mercury.app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
