"""Read quoted OneBot messages without downloading their attachments."""
from __future__ import annotations

from typing import Any

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment


def _message_from_payload(content: Any) -> Message:
    if isinstance(content, (Message, str, MessageSegment)):
        return Message(content)
    if isinstance(content, list):
        segments = []
        for item in content:
            if isinstance(item, MessageSegment):
                segments.append(item)
            elif isinstance(item, dict) and isinstance(item.get("type"), str) and isinstance(item.get("data"), dict):
                segments.append(MessageSegment(item["type"], dict(item["data"])))
            else:
                raise ValueError("Invalid quoted message segment")
        return Message(segments)
    raise ValueError("Invalid quoted message payload")


def reply_message_id(event: MessageEvent) -> int | str | None:
    reply = getattr(event, "reply", None)
    if reply is not None:
        message_id = getattr(reply, "message_id", None)
        if message_id is not None:
            return message_id
        segment = getattr(reply, "segment", None)
        if segment is not None and isinstance(segment.data, dict):
            return segment.data.get("id")
    for segment in event.message:
        if segment.type == "reply":
            return segment.data.get("id")
    return None


async def quoted_message(bot: Bot, event: MessageEvent) -> Message | None:
    reply = getattr(event, "reply", None)
    embedded = getattr(reply, "message", None)
    if embedded:
        return _message_from_payload(embedded)
    message_id = reply_message_id(event)
    if message_id is None:
        return None
    payload = await bot.call_api("get_msg", message_id=message_id)
    if not isinstance(payload, dict):
        raise ValueError("Invalid quoted message")
    content = payload.get("message", payload.get("raw_message"))
    if content is None:
        raise ValueError("Quoted message is unavailable")
    return _message_from_payload(content)


def message_text(message: Message) -> str:
    """Include bridge-provided image summaries, but never attachment URLs."""
    parts: list[str] = []
    for segment in message:
        if segment.type == "text":
            parts.append(str(segment.data.get("text", "")))
        elif segment.type in {"image", "mface"}:
            parts.append(str(segment.data.get("summary", "")))
    return "\n".join(parts)
