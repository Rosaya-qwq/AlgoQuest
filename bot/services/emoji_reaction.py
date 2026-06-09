from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_CQ_FACE_RE = re.compile(r"\[CQ:face,[^\]]*id=([^,\]]+)")
_CQ_MFACE_RE = re.compile(r"\[CQ:(?:mface|image),[^\]]*emoji_id=([^,\]]+)")


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
        if segment_type == "image" and (data.get("emoji_id") or data.get("emojiId")):
            emoji_segments += 1
            continue
        return False
    return emoji_segments == 1


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
