"""Start the local Repo Doctor web UI.

Usage:
    python scripts/serve.py
    python scripts/serve.py --port 9000 --no-browser
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

from repo_doctor.web.server import main  # noqa: E402


if __name__ == "__main__":
    main()
