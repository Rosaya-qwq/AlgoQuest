"""Rename a quoted image's QQ preview using the OneBot summary extension."""
from __future__ import annotations

from nonebot.adapters.onebot.v11 import Message, MessageSegment


def quoted_media(message: Message) -> MessageSegment | None:
    media = [segment for segment in message if segment.type in {"image", "mface"}]
    if len(media) > 1:
        raise ValueError("引用消息包含多张图片或表情包，请引用只有一张的消息。")
    return media[0] if media else None


def renamed_media(media: MessageSegment, name: str) -> MessageSegment:
    name = name.strip()
    if not name or len(name) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("名称须为 1–80 个字符，不能包含换行或控制字符。")
    data = media.data
    # Reuse the original URL/file identifier. The bot never downloads or saves it.
    source = data.get("url") or data.get("file")
    if source:
        if not isinstance(source, str):
            raise ValueError("引用图片的地址不可用。")
        return MessageSegment("image", {
            "file": source,
            "summary": name,
            "sub_type": 1,
        })
    if media.type == "mface" and data.get("emoji_id") and data.get("emoji_package_id") and data.get("key"):
        # Native market stickers may be represented only by their package metadata.
        payload = {key: data[key] for key in ("emoji_id", "emoji_package_id", "key")}
        payload["summary"] = name
        return MessageSegment("mface", payload)
    raise ValueError("引用消息没有可重发的图片地址或完整表情包信息。")
