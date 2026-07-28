from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def runtime_data_dir() -> Path:
    configured = os.environ.get("ALGOQUEST_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "data"
