from __future__ import annotations

import base64
import binascii
import io
import ipaddress
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from PIL import Image

from bot.services.group_config import search_enabled_for_event
from bot.services.permissions import is_superuser
from bot.services.web_search import MAX_IMAGES, SearchRejected, search_web


__plugin_meta__ = PluginMetadata(
    name="联网搜索",
    description="使用 DeepSeek 搜索网页并整理结果。",
    usage="/search [关键词] [图片]",
)

search_cmd = on_command("search", priority=5, block=True)


@search_cmd.handle()
async def handle_search(bot: Bot, event: Event, args: Message = CommandArg()) -> None:
    if not is_superuser(event) and not search_enabled_for_event(event):
        await search_cmd.finish()
    try:
        image_urls = _input_image_urls(event)
        reply = await search_web(args.extract_plain_text(), image_urls)
    except ValueError as exc:
        await search_cmd.finish(_reply_prefix(event) + MessageSegment.text(str(exc)))
    except SearchRejected as exc:
        await search_cmd.finish(_reply_prefix(event) + MessageSegment.text(str(exc)))
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.exception("DeepSeek web search failed")
        await search_cmd.finish(_reply_prefix(event) + MessageSegment.text(f"搜索失败：{exc}"))

    await bot.send(event, _reply_prefix(event) + MessageSegment.text(reply.text))
    if reply.image_urls:
        with tempfile.TemporaryDirectory(prefix="algoquest-search-") as temp_dir:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
                for index, image_url in enumerate(reply.image_urls[:MAX_IMAGES], start=1):
                    try:
                        image_data, suffix = await _download_image(client, image_url)
                        image_path = Path(temp_dir) / f"image-{index}{suffix}"
                        image_path.write_bytes(image_data)
                    except Exception:
                        logger.warning(f"Skipped unavailable search image {index}")
                        continue
                    await bot.send(
                        event,
                        _reply_prefix(event) + MessageSegment.image(image_path.resolve().as_uri()),
                    )
    await search_cmd.finish()


def _reply_prefix(event: Event) -> Message:
    message_id = getattr(event, "message_id", None)
    if isinstance(event, MessageEvent) and isinstance(message_id, int):
        return Message(MessageSegment.reply(message_id))
    return Message()


def _input_image_urls(event: Event) -> tuple[str, ...]:
    if not isinstance(event, MessageEvent):
        return ()
    images: list[str] = []
    for segment in event.message:
        if segment.type != "image":
            continue
        if len(images) >= MAX_IMAGES:
            raise ValueError(f"一次最多发送 {MAX_IMAGES} 张图片。")
        url = str(segment.data.get("url") or segment.data.get("file") or "").strip()
        if url.startswith("base64://"):
            data = url.removeprefix("base64://")
            try:
                decoded = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("消息图片数据无效。") from exc
            if len(decoded) > 5 * 1024 * 1024:
                raise ValueError("单张消息图片不能超过 5 MB。")
            url = f"data:image/png;base64,{data}"
        if not url.startswith(("http://", "https://", "data:image/")):
            raise ValueError("无法读取消息中的图片链接。")
        if url.startswith("data:image/") and len(url) > 7 * 1024 * 1024:
            raise ValueError("单张消息图片不能超过 5 MB。")
        if url.startswith(("http://", "https://")) and len(url) > 8192:
            raise ValueError("消息图片链接过长。")
        images.append(url)
    return tuple(images)


async def _download_image(client: httpx.AsyncClient, url: str) -> tuple[bytes, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("图片地址无效")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
            raise ValueError("图片地址无效")
    else:
        if not address.is_global:
            raise ValueError("图片地址无效")
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        image_data = bytearray()
        async for chunk in response.aiter_bytes():
            image_data.extend(chunk)
            if len(image_data) > 5 * 1024 * 1024:
                raise ValueError("图片过大")
    with Image.open(io.BytesIO(image_data)) as image:
        suffix = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "WEBP": ".webp"}.get(image.format or "")
        if suffix is None:
            raise ValueError("不支持的图片格式")
        if image.width * image.height > 25_000_000:
            raise ValueError("图片尺寸过大")
        image.verify()
    return bytes(image_data), suffix
