from nonebot import on_command
from nonebot.adapters.onebot.v11 import Event
from nonebot.plugin import PluginMetadata

from bot.services.problem_random import difficulty_usage
from bot.services.help_text import admin_help_text, user_help_text
from bot.services.permissions import is_superuser


__plugin_meta__ = PluginMetadata(
    name="基础指令",
    description="提供机器人连通性测试和帮助指令。",
    usage="/help\n/ping\n/giveup <cf|at> <难度>\n/cur <cf|at> <难度>\n/submit <cf|at> <难度> <题解描述>\n/rank",
)


help_cmd = on_command("help", aliases={"帮助"}, priority=5, block=True)
ping_cmd = on_command("ping", aliases={"状态"}, priority=5, block=True)


@help_cmd.handle()
async def handle_help(event: Event) -> None:
    help_text = user_help_text()
    if is_superuser(event):
        help_text += "\n\n管理员命令：\n" + admin_help_text()
    await help_cmd.finish(help_text + "\n\n" + difficulty_usage())


@ping_cmd.handle()
async def handle_ping() -> None:
    await ping_cmd.finish("pong")
