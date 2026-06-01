from __future__ import annotations

import os
from pathlib import Path
from string import Formatter
from typing import Any

from dotenv import load_dotenv


_env_path = Path(".env")
if _env_path.exists():
    load_dotenv(_env_path)


DEFAULT_APP_NAME = "AlgoQuest"


def env_text(key: str, default: str) -> str:
    value = os.environ.get(key)
    if value is None or not value.strip():
        return default
    return value.replace("\\n", "\n")


def app_name() -> str:
    return env_text("ALGOQUEST_DISPLAY_NAME", DEFAULT_APP_NAME)


def env_template(key: str, default: str, **values: Any) -> str:
    template = env_text(key, default)
    return _safe_format(template, values)


def _safe_format(template: str, values: dict[str, Any]) -> str:
    class SafeDict(dict[str, Any]):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    try:
        Formatter().parse(template)
        return template.format_map(SafeDict(values))
    except Exception:
        return template
