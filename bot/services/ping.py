"""Optional personal sticker response for /ping."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from nonebot.adapters.onebot.v11 import MessageSegment

from bot.services.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")


def ping_image() -> MessageSegment | None:
    if os.environ.get("ALGOQUEST_PING_IMAGE_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "enabled"}:
        return None
    source = os.environ.get("ALGOQUEST_PING_IMAGE_PATH", "").strip()
    if not source:
        raise ValueError("Ping image path is empty")
    if urlsplit(source).scheme not in {"http", "https"}:
        path = Path(source).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.is_file():
            raise FileNotFoundError("Ping image does not exist")
        source = path.resolve().as_uri()
    summary = os.environ.get("ALGOQUEST_PING_IMAGE_SUMMARY", "pong").strip() or "pong"
    return MessageSegment("image", {"file": source, "sub_type": 1, "summary": summary})
