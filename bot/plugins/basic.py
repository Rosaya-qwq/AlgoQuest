from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from bot.services.group_config import (
    format_group_config,
    get_group_config,
    group_bot_enabled,
    group_config_exists,
    group_id_from_event,
    init_args_to_config,
    parse_init_config_args,
    set_group_config,
)
from bot.services.problem_random import difficulty_usage
from bot.services.help_text import admin_help_text, group_help_text
from bot.services.permissions import is_group_admin, is_superuser


__plugin_meta__ = PluginMetadata(
    name="基础指令",
    description="提供机器人连通性测试和帮助指令。",
    usage="/help\n/ping\n/giveup <cf|at> <难度>\n/cur <cf|at> <难度>\n/submit <cf|at> <难度> <题解描述>\n/rank",
)


help_cmd = on_command("help", aliases={"帮助"}, priority=5, block=True)
ping_cmd = on_command("ping", aliases={"状态"}, priority=5, block=True)
init_cmd = on_command("init", aliases={"初始化"}, priority=4, block=True)
config_cmd = on_command("config", aliases={"配置"}, priority=5, block=True)


@help_cmd.handle()
async def handle_help(bot: Bot, event: Event) -> None:
    group_id = group_id_from_event(event)
    superuser = is_superuser(event)
    if not superuser and not group_bot_enabled(group_id):
        await help_cmd.finish()
    config = get_group_config(group_id)
    help_text = group_help_text(config)
    if superuser:
        help_text += "\n\n管理员命令：\n" + admin_help_text()
    elif config.algo_enabled and await is_group_admin(bot, event):
        help_text += (
            "\n\n群管理命令：\n"
            "/giveup <cf|at> <难度> - 直接放弃当前题并刷新\n"
            "/pass <cf|at> <难度> - 回复用户提交消息，强制当前题通过\n"
            "/rank - 查看全体排行榜卡片"
        )
    if config.algo_enabled:
        help_text += "\n\n" + difficulty_usage()
    await help_cmd.finish(help_text)


@ping_cmd.handle()
async def handle_ping(event: Event) -> None:
    if not is_superuser(event) and not group_bot_enabled(group_id_from_event(event)):
        await ping_cmd.finish()
    await ping_cmd.finish("pong")


@init_cmd.handle()
async def handle_init(event: Event, args: Message = CommandArg()) -> None:
    if not is_superuser(event):
        await init_cmd.finish()
    if not isinstance(event, GroupMessageEvent):
        await init_cmd.finish("只能在群聊中使用 /init。")

    parsed = parse_init_config_args(args.extract_plain_text())
    if parsed is None:
        await init_cmd.finish(_init_usage())

    config = init_args_to_config(parsed)
    set_group_config(event.group_id, config)
    await init_cmd.finish("已更新当前群配置。\n" + format_group_config(event.group_id, config))


@config_cmd.handle()
async def handle_config(event: Event) -> None:
    if not isinstance(event, GroupMessageEvent):
        await config_cmd.finish("私聊没有群配置。")
    if not is_superuser(event) and not group_config_exists(event.group_id):
        await config_cmd.finish()
    config = get_group_config(event.group_id)
    await config_cmd.finish(format_group_config(event.group_id, config))


def _init_usage() -> str:
    return (
        "用法：/init <algo:enable|disable> <rank:self|all> <giveup:count> <emoji:enable|disable>\n"
        "例如：/init algo:enable rank:self giveup:2 emoji:disable"
    )
