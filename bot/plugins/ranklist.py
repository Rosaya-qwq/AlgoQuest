from __future__ import annotations

from pathlib import Path
from typing import Any

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message, MessageSegment
from nonebot.log import logger
from nonebot.plugin import PluginMetadata

from bot.services.group_config import algo_enabled_for_event, rank_mode_for_event
from bot.services.permissions import get_event_user_id, is_group_admin, is_superuser
from bot.services.ranklist import render_ranklist_image, render_user_rank_image
from bot.services.submission import remove_rank_user


__plugin_meta__ = PluginMetadata(
    name="排行榜",
    description="按 solved 字符串输出成功解题用户排行榜图片。",
    usage="/rank",
)


rank_cmd = on_command("rank", aliases={"排行榜", "排名"}, priority=5, block=True)


@rank_cmd.handle()
async def handle_rank(bot: Bot, event: Event) -> None:
    superuser = is_superuser(event)
    if not superuser and not algo_enabled_for_event(event):
        await rank_cmd.finish()

    remove_rank_user(str(bot.self_id))
    try:
        can_view_all = superuser or rank_mode_for_event(event) == "all" or await is_group_admin(bot, event)
        if can_view_all:
            user_names = await _resolve_rank_user_names(bot, event)
            image_path = await render_ranklist_image(user_names=user_names)
        else:
            user_id = get_event_user_id(event)
            if user_id is None:
                await rank_cmd.finish("无法识别用户。")
            user_names = {user_id: await _resolve_user_name(bot, event, user_id)}
            image_path = await render_user_rank_image(user_id, user_names=user_names)
    except Exception as exc:
        logger.exception("Failed to render ranklist")
        await rank_cmd.finish(f"排行榜生成失败：{exc}")

    await bot.send(event, Message(MessageSegment.image(Path(image_path).resolve().as_uri())))
    await rank_cmd.finish()


async def _resolve_rank_user_names(bot: Bot, event: Event) -> dict[str, str]:
    from bot.services.submission import get_rank_entries

    entries = get_rank_entries()[:30]
    user_names: dict[str, str] = {}
    for entry in entries:
        user_id = str(entry["user_id"])
        user_names[user_id] = await _resolve_user_name(bot, event, user_id)
    return user_names


async def _resolve_user_name(bot: Bot, event: Event, user_id: str) -> str:
    if isinstance(event, GroupMessageEvent):
        group_name = await _get_group_user_name(bot, event.group_id, user_id)
        if group_name:
            return group_name

    stranger_name = await _get_stranger_user_name(bot, user_id)
    return stranger_name or f"用户 {user_id}"


async def _get_group_user_name(bot: Bot, group_id: int, user_id: str) -> str | None:
    try:
        data = await bot.call_api("get_group_member_info", group_id=group_id, user_id=int(user_id), no_cache=False)
    except Exception:
        logger.warning(f"Failed to fetch group member info for {user_id}")
        return None
    return _pick_display_name(data)


async def _get_stranger_user_name(bot: Bot, user_id: str) -> str | None:
    try:
        data = await bot.call_api("get_stranger_info", user_id=int(user_id), no_cache=False)
    except Exception:
        logger.warning(f"Failed to fetch stranger info for {user_id}")
        return None
    return _pick_display_name(data)


def _pick_display_name(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("card", "nickname", "user_name"):
        value = str(data.get(key, "")).strip()
        if value:
            return value
    return None
