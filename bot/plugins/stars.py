from __future__ import annotations

import sqlite3

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from bot.services.group_config import algo_enabled_for_event
from bot.services.message_refs import message_text, quoted_message, reply_message_id
from bot.services.permissions import is_superuser
from bot.services.stars import (
    extract_problem_ids, format_star_pages, list_stars, normalize_problem_id,
    parse_star_args, solution_message_problem, update_star,
)

__plugin_meta__ = PluginMetadata(name="题目收藏", description="每位用户独立收藏 CF / AtCoder 题目。", usage="/star [+-] [题号]")
star_cmd = on_command("star", aliases={"收藏题目"}, priority=5, block=True)
USAGE = "用法：/star 查询；/star [+|-] CF2062A 或 AT_arc017_1；也可引用题解发送 /star 或 /star -。"


@star_cmd.handle()
async def handle_star(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    if not is_superuser(event) and not algo_enabled_for_event(event):
        await star_cmd.finish()
    text = args.extract_plain_text().strip()
    action, identifier = parse_star_args(text)
    quoted_id = reply_message_id(event)
    user_id = str(event.user_id)
    try:
        if not text and quoted_id is None:
            pages = format_star_pages(list_stars(user_id))
            for page in pages:
                await star_cmd.send(page)
        else:
            problem = normalize_problem_id(identifier) if identifier else None
            if identifier and problem is None:
                await star_cmd.finish("题号格式无效。" + USAGE)
            if not identifier:
                if quoted_id is None:
                    await star_cmd.finish(USAGE)
                problem = solution_message_problem(str(bot.self_id), quoted_id)
                if problem is None:
                    try:
                        message = await quoted_message(bot, event)
                    except Exception as exc:
                        logger.warning(f"Cannot read quoted message for /star ({type(exc).__name__})")
                        await star_cmd.finish("无法读取引用消息，请直接输入题号。" + USAGE)
                    candidates = extract_problem_ids(message_text(message)) if message else []
                    if len(candidates) != 1:
                        detail = "引用消息包含多个题号，请直接指定其中一个。" if candidates else "未找到 CF/AT 题号；旧的纯图片题解请直接输入题号。"
                        await star_cmd.finish(detail + USAGE)
                    problem = candidates[0]
            changed = update_star(user_id, problem, add=action == "+")
            if action == "+":
                result = "已加入你的收藏题单" if changed else "已在你的收藏题单中"
            else:
                result = "已从你的收藏题单移除" if changed else "不在你的收藏题单中"
            await star_cmd.send(f"{problem.canonical} {result}。")
    except (OSError, sqlite3.Error) as exc:
        logger.warning(f"Cannot update/read problem bookmarks ({type(exc).__name__})")
        await star_cmd.finish("收藏题单暂时无法读写，请稍后重试。")
    await star_cmd.finish()
