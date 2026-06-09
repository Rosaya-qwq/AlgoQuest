from __future__ import annotations

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from bot.services.emoji_reaction import extract_emoji_id, is_single_super_emoji_message
from bot.services.permissions import is_superuser


__plugin_meta__ = PluginMetadata(
    name="表情回应",
    description="超级管理员给消息贴 QQ 表情回应。",
    usage="/emoji <QQ表情>",
)


emoji_cmd = on_command("emoji", aliases={"贴表情"}, priority=4, block=True)
auto_super_emoji = on_message(priority=20, block=False)


@emoji_cmd.handle()
async def handle_emoji(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    if not is_superuser(event):
        await emoji_cmd.finish("只有超级管理员可以使用 /emoji。")

    emoji_id = extract_emoji_id(args)
    if emoji_id is None:
        await emoji_cmd.finish("表情不可用。")

    target_message_id = _reply_message_id(event) or getattr(event, "message_id", None)
    if target_message_id is None:
        await emoji_cmd.finish("表情不可用。")

    if not await _set_msg_emoji_like(bot, target_message_id, emoji_id):
        await emoji_cmd.finish("表情不可用。")
    await emoji_cmd.finish()


@auto_super_emoji.handle()
async def handle_auto_super_emoji(bot: Bot, event: MessageEvent) -> None:
    if not is_superuser(event):
        return
    if not is_single_super_emoji_message(event.message):
        return

    emoji_id = extract_emoji_id(event.message, allow_text=False)
    message_id = getattr(event, "message_id", None)
    if emoji_id is None or message_id is None:
        return
    if not await _set_msg_emoji_like(bot, message_id, emoji_id):
        return


async def _set_msg_emoji_like(bot: Bot, message_id: int | str, emoji_id: str) -> bool:
    last_error: Exception | None = None
    payloads = (
        {"message_id": message_id, "emoji_id": str(emoji_id), "set": True},
        {"message_id": message_id, "emoji_id": str(emoji_id)},
    )
    for payload in payloads:
        try:
            await bot.call_api("set_msg_emoji_like", **payload)
            return True
        except Exception as exc:
            last_error = exc
    logger.warning(
        f"Failed to set message emoji like: message_id={message_id}, "
        f"emoji_id={emoji_id}, error={last_error!r}"
    )
    return False


def _reply_message_id(event: MessageEvent) -> int | str | None:
    reply = getattr(event, "reply", None)
    if reply is None:
        return None
    message_id = getattr(reply, "message_id", None)
    if message_id is not None:
        return message_id
    segment = getattr(reply, "segment", None)
    data = getattr(segment, "data", {}) if segment is not None else {}
    if isinstance(data, dict):
        return data.get("id")
    return None
