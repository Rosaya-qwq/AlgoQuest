from __future__ import annotations

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, MessageEvent


def get_event_user_id(event: Event) -> str | None:
    if isinstance(event, MessageEvent):
        return str(event.user_id)
    user_id = getattr(event, "user_id", None)
    return str(user_id) if user_id is not None else None


def is_superuser(event: Event) -> bool:
    user_id = get_event_user_id(event)
    if user_id is None:
        return False
    return user_id in set(get_driver().config.superusers)


async def is_group_admin_or_superuser(bot: Bot, event: Event) -> bool:
    if is_superuser(event):
        return True
    if not isinstance(event, GroupMessageEvent):
        return False
    user_id = get_event_user_id(event)
    if user_id is None:
        return False
    try:
        info = await bot.call_api(
            "get_group_member_info",
            group_id=event.group_id,
            user_id=int(user_id),
            no_cache=False,
        )
    except Exception:
        return False
    role = str(info.get("role", "")) if isinstance(info, dict) else ""
    return role in {"owner", "admin"}
