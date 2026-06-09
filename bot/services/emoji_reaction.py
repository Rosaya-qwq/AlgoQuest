from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from nonebot.log import logger


_CQ_FACE_RE = re.compile(r"\[CQ:face,[^\]]*id=([^,\]]+)")
_CQ_MFACE_RE = re.compile(r"\[CQ:(?:mface|image),[^\]]*emoji_id=([^,\]]+)")
LEARNED_EMOJI_PATH = Path("data/emoji_reactions/learned.json")
TEXT_EMOJI_ID_ALIASES = {
    "㊗": "12951",
    "㊗️": "12951",
    "祝": "12951",
}


def extract_emoji_id(message: Iterable[Any], *, allow_text: bool = True) -> str | None:
    """Extract a NapCat set_msg_emoji_like emoji id from a message.

    QQ built-in faces use ``face.id``.  QQ mall/super expressions may arrive as
    ``mface.emoji_id`` or as an ``image`` segment carrying ``emoji_id``.
    """
    for segment in message:
        segment_type = _segment_type(segment)
        data = _segment_data(segment)
        if segment_type == "face":
            value = data.get("id")
            if value:
                return str(value)
        if segment_type in {"mface", "image"}:
            value = data.get("emoji_id") or data.get("emojiId")
            if value:
                return str(value)

    if not allow_text:
        return None

    text = _plain_text(message)
    cq_value = _extract_cq_emoji_id(text)
    if cq_value:
        return cq_value
    text = text.strip()
    alias = TEXT_EMOJI_ID_ALIASES.get(text)
    if alias:
        return alias
    if text.isdigit():
        return text
    if text and len(text) <= 8 and not any(ch.isspace() for ch in text):
        return text
    return None


def is_single_super_emoji_message(message: Iterable[Any]) -> bool:
    """Return True when the message is only a QQ mall/super expression."""
    emoji_segments = 0
    for segment in message:
        segment_type = _segment_type(segment)
        data = _segment_data(segment)
        if segment_type == "text":
            if str(data.get("text") or "").strip():
                return False
            continue
        if segment_type == "mface":
            if data.get("emoji_id") or data.get("emojiId"):
                emoji_segments += 1
                continue
        if segment_type == "face" and _is_super_face(data):
            emoji_segments += 1
            continue
        if segment_type == "image" and (data.get("emoji_id") or data.get("emojiId")):
            emoji_segments += 1
            continue
        return False
    return emoji_segments == 1


def extract_notice_emoji_id(likes: Any) -> str | None:
    if not isinstance(likes, list):
        return None
    for like in reversed(likes):
        if not isinstance(like, dict):
            continue
        emoji_id = like.get("emoji_id")
        if emoji_id:
            return str(emoji_id)
    return None


def learn_reaction_emoji(emoji_id: str) -> bool:
    normalized = _normalize_emoji_id(emoji_id)
    if normalized is None:
        return False
    data = _load_learned_emojis()
    ids = set(data.get("emoji_ids", []))
    if normalized in ids:
        return False
    ids.add(normalized)
    data["emoji_ids"] = sorted(ids, key=_emoji_id_sort_key)
    _save_learned_emojis(data)
    return True


def learned_reaction_emojis() -> list[str]:
    return list(_load_learned_emojis().get("emoji_ids", []))


def _segment_type(segment: Any) -> str:
    if isinstance(segment, dict):
        return str(segment.get("type") or "")
    return str(getattr(segment, "type", "") or "")


def _segment_data(segment: Any) -> dict[str, Any]:
    if isinstance(segment, dict):
        data = segment.get("data") or {}
    else:
        data = getattr(segment, "data", {}) or {}
    return data if isinstance(data, dict) else {}


def _is_super_face(data: dict[str, Any]) -> bool:
    raw = data.get("raw")
    if not isinstance(raw, dict):
        return False
    try:
        return int(raw.get("faceType", 0)) == 3
    except (TypeError, ValueError):
        return False


def _plain_text(message: Iterable[Any]) -> str:
    parts: list[str] = []
    for segment in message:
        if _segment_type(segment) != "text":
            continue
        parts.append(str(_segment_data(segment).get("text") or ""))
    return "".join(parts)


def _extract_cq_emoji_id(text: str) -> str | None:
    for pattern in (_CQ_MFACE_RE, _CQ_FACE_RE):
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _normalize_emoji_id(value: str) -> str | None:
    emoji_id = str(value).strip()
    if not re.fullmatch(r"\d{1,12}", emoji_id):
        return None
    return emoji_id


def _load_learned_emojis() -> dict[str, list[str]]:
    if not LEARNED_EMOJI_PATH.exists():
        return {"emoji_ids": []}
    try:
        data = json.loads(LEARNED_EMOJI_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load learned emoji reactions")
        return {"emoji_ids": []}
    if not isinstance(data, dict):
        return {"emoji_ids": []}
    raw_ids = data.get("emoji_ids", [])
    if not isinstance(raw_ids, list):
        return {"emoji_ids": []}
    ids = {
        emoji_id
        for item in raw_ids
        if (emoji_id := _normalize_emoji_id(str(item))) is not None
    }
    return {"emoji_ids": sorted(ids, key=_emoji_id_sort_key)}


def _save_learned_emojis(data: dict[str, Any]) -> None:
    LEARNED_EMOJI_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEARNED_EMOJI_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _emoji_id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)
