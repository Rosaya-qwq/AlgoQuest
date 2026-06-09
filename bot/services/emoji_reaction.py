from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from nonebot.log import logger


_CQ_FACE_RE = re.compile(r"\[CQ:face,[^\]]*id=([^,\]]+)")
_CQ_MFACE_RE = re.compile(r"\[CQ:(?:mface|image),[^\]]*emoji_id=([^,\]]+)")
EMOJI_BINDINGS_PATH = Path("data/emoji_reactions/bindings.json")
DEFAULT_TEXT_EMOJI_ID_BINDINGS = {
    "㊗️": "12951",
}


@dataclass(frozen=True)
class EmojiBindingAction:
    action: Literal["bind", "remove"]
    emoji: str
    emoji_id: str


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
    if text.isdigit():
        return text
    emoji_id = emoji_binding_for(text)
    if emoji_id:
        return emoji_id
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


def parse_emoji_binding_action(message: Iterable[Any]) -> EmojiBindingAction | None:
    text = _plain_text(message).strip()
    if not has_emoji_binding_operator(message):
        return None
    operator = "!=" if "!=" in text else "="
    raw_emoji, raw_emoji_id = text.split(operator, 1)
    emoji = _normalize_unicode_emoji(raw_emoji)
    emoji_id = _normalize_emoji_id(raw_emoji_id)
    if emoji is None or emoji_id is None:
        return None
    action: Literal["bind", "remove"] = "remove" if operator == "!=" else "bind"
    return EmojiBindingAction(action=action, emoji=emoji, emoji_id=emoji_id)


def has_emoji_binding_operator(message: Iterable[Any]) -> bool:
    text = _plain_text(message).strip()
    return "!=" in text or "=" in text


def set_unicode_emoji_binding(emoji: str, emoji_id: str) -> bool:
    normalized_emoji = _normalize_unicode_emoji(emoji)
    normalized_id = _normalize_emoji_id(emoji_id)
    if normalized_emoji is None or normalized_id is None:
        return False
    bindings = emoji_bindings()
    if bindings.get(normalized_emoji) == normalized_id:
        return False
    bindings[normalized_emoji] = normalized_id
    _save_emoji_bindings(bindings)
    return True


def remove_unicode_emoji_binding(emoji: str, emoji_id: str) -> bool:
    normalized_emoji = _normalize_unicode_emoji(emoji)
    normalized_id = _normalize_emoji_id(emoji_id)
    if normalized_emoji is None or normalized_id is None:
        return False
    bindings = emoji_bindings()
    if bindings.get(normalized_emoji) != normalized_id:
        return False
    del bindings[normalized_emoji]
    _save_emoji_bindings(bindings)
    return True


def emoji_binding_for(emoji: str) -> str | None:
    normalized_emoji = _normalize_unicode_emoji(emoji)
    if normalized_emoji is None:
        return None
    return emoji_bindings().get(normalized_emoji)


def emoji_bindings() -> dict[str, str]:
    return _load_emoji_bindings()


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


def _normalize_unicode_emoji(value: str) -> str | None:
    emoji = str(value).strip()
    if (
        not emoji
        or len(emoji) > 16
        or emoji.isdigit()
        or "[CQ:" in emoji
        or any(ch.isspace() for ch in emoji)
    ):
        return None
    if not any(_is_emoji_codepoint(ord(ch)) for ch in emoji):
        return None
    return emoji


def _is_emoji_codepoint(codepoint: int) -> bool:
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x2B00 <= codepoint <= 0x2BFF
        or 0x3000 <= codepoint <= 0x303F
        or 0x3200 <= codepoint <= 0x32FF
        or codepoint == 0x20E3
    )


def _load_emoji_bindings() -> dict[str, str]:
    if not EMOJI_BINDINGS_PATH.exists():
        return dict(DEFAULT_TEXT_EMOJI_ID_BINDINGS)
    try:
        data = json.loads(EMOJI_BINDINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load emoji bindings")
        return dict(DEFAULT_TEXT_EMOJI_ID_BINDINGS)
    if not isinstance(data, dict):
        return dict(DEFAULT_TEXT_EMOJI_ID_BINDINGS)
    raw_bindings = data.get("bindings")
    if not isinstance(raw_bindings, dict):
        return dict(DEFAULT_TEXT_EMOJI_ID_BINDINGS)
    bindings: dict[str, str] = {}
    for raw_emoji, raw_emoji_id in raw_bindings.items():
        emoji = _normalize_unicode_emoji(str(raw_emoji))
        emoji_id = _normalize_emoji_id(str(raw_emoji_id))
        if emoji is not None and emoji_id is not None:
            bindings[emoji] = emoji_id
    return dict(sorted(bindings.items(), key=lambda item: item[0]))


def _save_emoji_bindings(bindings: dict[str, str]) -> None:
    EMOJI_BINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"bindings": dict(sorted(bindings.items(), key=lambda item: item[0]))}
    EMOJI_BINDINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
