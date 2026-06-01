from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nonebot.log import logger


BLACKLIST_PATH = Path("data/blacklist/users.json")


def normalize_uid(raw_uid: str) -> str | None:
    uid = raw_uid.strip()
    if not re.fullmatch(r"\d{5,12}", uid):
        return None
    return uid


def is_blacklisted(user_id: str) -> bool:
    return user_id in set(_load_blacklist().get("users", []))


def add_to_blacklist(user_id: str) -> bool:
    data = _load_blacklist()
    users = set(data.get("users", []))
    if user_id in users:
        return False
    users.add(user_id)
    data["users"] = sorted(users, key=lambda item: int(item))
    _save_blacklist(data)
    return True


def remove_from_blacklist(user_id: str) -> bool:
    data = _load_blacklist()
    users = set(data.get("users", []))
    if user_id not in users:
        return False
    users.remove(user_id)
    data["users"] = sorted(users, key=lambda item: int(item))
    _save_blacklist(data)
    return True


def _load_blacklist() -> dict[str, list[str]]:
    if not BLACKLIST_PATH.exists():
        return {"users": []}
    try:
        data = json.loads(BLACKLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load blacklist")
        return {"users": []}

    if not isinstance(data, dict):
        return {"users": []}
    raw_users = data.get("users", [])
    if not isinstance(raw_users, list):
        return {"users": []}

    users = sorted(
        {
            uid
            for item in raw_users
            if (uid := normalize_uid(str(item))) is not None
        },
        key=lambda item: int(item),
    )
    return {"users": users}


def _save_blacklist(data: dict[str, Any]) -> None:
    BLACKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    BLACKLIST_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
