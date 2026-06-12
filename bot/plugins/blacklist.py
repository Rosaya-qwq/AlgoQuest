from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Event, Message
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from bot.services.blacklist import add_to_blacklist, is_blacklisted, normalize_uid, remove_from_blacklist
from bot.services.permissions import get_event_user_id, is_superuser
from bot.services.submission import remove_rank_user


__plugin_meta__ = PluginMetadata(
    name="黑名单管理",
    description="管理员维护不能使用机器人指令的用户 uid。",
    usage="/add <uid>\n/remove <uid>\n/del <uid>",
)


add_cmd = on_command("add", aliases={"拉黑"}, priority=4, block=True)
remove_cmd = on_command("remove", aliases={"移除黑名单"}, priority=4, block=True)
del_cmd = on_command("del", aliases={"删除榜单"}, priority=4, block=True)


@event_preprocessor
async def block_blacklisted_users(event: Event) -> None:
    if is_superuser(event):
        return
    user_id = get_event_user_id(event)
    if user_id is not None and is_blacklisted(user_id):
        raise IgnoredException("blacklisted user")


@add_cmd.handle()
async def handle_add(event: Event, args: Message = CommandArg()) -> None:
    if not is_superuser(event):
        await add_cmd.finish()

    uid = normalize_uid(args.extract_plain_text())
    if uid is None:
        await add_cmd.finish("用法：/add <uid>")

    changed = add_to_blacklist(uid)
    if changed:
        await add_cmd.finish(f"已加入黑名单：{uid}")
    await add_cmd.finish(f"{uid} 已在黑名单中。")


@remove_cmd.handle()
async def handle_remove(event: Event, args: Message = CommandArg()) -> None:
    if not is_superuser(event):
        await remove_cmd.finish()

    uid = normalize_uid(args.extract_plain_text())
    if uid is None:
        await remove_cmd.finish("用法：/remove <uid>")

    changed = remove_from_blacklist(uid)
    if changed:
        await remove_cmd.finish(f"已移出黑名单：{uid}")
    await remove_cmd.finish(f"{uid} 不在黑名单中。")


@del_cmd.handle()
async def handle_del(event: Event, args: Message = CommandArg()) -> None:
    if not is_superuser(event):
        await del_cmd.finish()

    uid = normalize_uid(args.extract_plain_text())
    if uid is None:
        await del_cmd.finish("用法：/del <uid>")

    changed = remove_rank_user(uid)
    if changed:
        await del_cmd.finish(f"已删除榜单用户数据：{uid}")
    await del_cmd.finish(f"{uid} 不在榜单数据中。")
