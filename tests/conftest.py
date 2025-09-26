import os
import sys
from pathlib import Path

def pytest_sessionstart(session):
    # Ensure headless Qt where applicable
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Ensure src is on sys.path without needing plugins
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
