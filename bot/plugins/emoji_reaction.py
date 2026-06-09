from __future__ import annotations

from nonebot import on_command, on_message, on_notice
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, NoticeEvent
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from bot.services.emoji_reaction import (
    auto_unicode_binding_action,
    emoji_bindings,
    extract_emoji_id,
    extract_notice_emoji_id,
    is_single_reaction_emoji_message,
    is_single_super_emoji_message,
    parse_emoji_binding_action,
    remove_unicode_emoji_binding,
    set_unicode_emoji_binding,
)
from bot.services.permissions import is_superuser


__plugin_meta__ = PluginMetadata(
    name="表情回应",
    description="超级管理员给消息贴 QQ 表情回应。",
    usage="/emoji <表情或ID>\n/emojilist",
)


emoji_cmd = on_command("emoji", aliases={"贴表情"}, priority=4, block=True)
emoji_list_cmd = on_command("emojilist", aliases={"表情列表"}, priority=4, block=True)
auto_emoji = on_message(priority=20, block=False)
emoji_like_notice = on_notice(priority=20, block=False)


@emoji_cmd.handle()
async def handle_emoji(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    if not is_superuser(event):
        await emoji_cmd.finish("只有超级管理员可以使用 /emoji。")

    binding_action = parse_emoji_binding_action(args)
    if binding_action is not None:
        if binding_action.action == "bind":
            changed = set_unicode_emoji_binding(binding_action.emoji, binding_action.emoji_id)
            suffix = "已绑定" if changed else "绑定未变化"
            await emoji_cmd.finish(f"{suffix}：{binding_action.emoji} = {binding_action.emoji_id}")
        removed = remove_unicode_emoji_binding(binding_action.emoji, binding_action.emoji_id)
        if removed:
            await emoji_cmd.finish(f"已删除绑定：{binding_action.emoji} != {binding_action.emoji_id}")
        await emoji_cmd.finish("没有找到对应绑定。")

    emoji_id = extract_emoji_id(args)
    if emoji_id is None:
        await emoji_cmd.finish("表情不可用。")
    auto_binding_action = auto_unicode_binding_action(args)

    target_message_id = _reply_message_id(event) or getattr(event, "message_id", None)
    if target_message_id is None:
        await emoji_cmd.finish("表情不可用。")

    if not await _set_msg_emoji_like(bot, target_message_id, emoji_id):
        await emoji_cmd.finish("表情不可用。")
    if auto_binding_action is not None:
        set_unicode_emoji_binding(auto_binding_action.emoji, auto_binding_action.emoji_id)
    await emoji_cmd.finish()


@emoji_list_cmd.handle()
async def handle_emoji_list(event: MessageEvent) -> None:
    if not is_superuser(event):
        await emoji_list_cmd.finish("只有超级管理员可以使用 /emojilist。")

    bindings = emoji_bindings()
    if not bindings:
        await emoji_list_cmd.finish("还没有绑定 Unicode 表情。")

    rows = [f"{emoji} = {emoji_id}" for emoji, emoji_id in bindings.items()]
    await emoji_list_cmd.finish("已绑定 Unicode 表情：\n" + "\n".join(rows))


@auto_emoji.handle()
async def handle_auto_emoji(bot: Bot, event: MessageEvent) -> None:
    if not is_superuser(event):
        return
    if not is_single_reaction_emoji_message(event.message):
        return

    emoji_id = extract_emoji_id(event.message)
    message_id = getattr(event, "message_id", None)
    if emoji_id is None or message_id is None:
        return
    if not await _set_msg_emoji_like(bot, message_id, emoji_id):
        return
    auto_binding_action = auto_unicode_binding_action(event.message)
    if auto_binding_action is not None:
        set_unicode_emoji_binding(auto_binding_action.emoji, auto_binding_action.emoji_id)


@emoji_like_notice.handle()
async def handle_emoji_like_notice(bot: Bot, event: NoticeEvent) -> None:
    if not is_superuser(event):
        return
    if getattr(event, "notice_type", None) != "group_msg_emoji_like":
        return
    if getattr(event, "self_id", None) == getattr(event, "user_id", None):
        return
    if getattr(event, "is_add", True) is False:
        return

    message_id = getattr(event, "message_id", None)
    emoji_id = extract_notice_emoji_id(getattr(event, "likes", None))
    if message_id is None or emoji_id is None:
        return
    await _set_msg_emoji_like(bot, message_id, emoji_id)


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
