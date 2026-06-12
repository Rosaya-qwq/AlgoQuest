from __future__ import annotations

import asyncio
import time
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from bot.services.problem_random import (
    DIFFICULTIES_BY_SOURCE,
    RenderedProblem,
    difficulty_usage,
    giveup_to_next,
    get_current_problem,
    parse_source_difficulty_args,
    read_problem_markdown,
    read_problem_tutorial,
    warm_states_in_background,
)
from bot.services.group_config import algo_enabled_for_event, giveup_count_for_event, group_id_from_event
from bot.services.permissions import get_event_user_id, is_group_admin, is_superuser


__plugin_meta__ = PluginMetadata(
    name="随机算法题",
    description="按难度随机 Codeforces / AtCoder 题目，渲染题面和样例 PNG 后发送。",
    usage="/giveup cf easy",
)

giveup_cmd = on_command("giveup", aliases={"放弃", "random", "随机题"}, priority=5, block=True)
cur_cmd = on_command("cur", aliases={"当前题"}, priority=5, block=True)

# Per-difficulty lock to prevent concurrent renders racing.
_busy_locks: dict[str, asyncio.Lock] = {
    f"{source}:{key}": asyncio.Lock()
    for source, difficulties in DIFFICULTIES_BY_SOURCE.items()
    for key in difficulties
}
_giveup_votes: dict[str, set[str]] = {}
_giveup_immunity_until: dict[str, float] = {}
_giveup_running: set[str] = set()
_GIVEUP_IMMUNITY_SECONDS = 5 * 60


@giveup_cmd.handle()
async def handle_giveup(bot: Bot, event: Event, args: Message = CommandArg()) -> None:
    superuser = is_superuser(event)
    if not superuser and not algo_enabled_for_event(event):
        await giveup_cmd.finish()

    source, difficulty_key, _ = parse_source_difficulty_args(args.extract_plain_text(), require_source=True)
    if source is None or difficulty_key is None:
        await giveup_cmd.finish(difficulty_usage("/giveup"))

    difficulty = DIFFICULTIES_BY_SOURCE[source][difficulty_key]
    reply_prefix = _reply_to_event(event)
    state_key = f"{group_id_from_event(event) or 'global'}:{source}:{difficulty_key}"
    lock_key = f"{source}:{difficulty_key}"
    user_id = get_event_user_id(event) or "unknown"
    required_votes = giveup_count_for_event(event)
    privileged = superuser or await is_group_admin(bot, event)

    if not privileged:
        now = time.time()
        if state_key in _giveup_running:
            await giveup_cmd.finish(
                reply_prefix
                + MessageSegment.text("当前题正在执行放弃并刷新，本次请求不计入新题投票。")
            )
        immunity_until = _giveup_immunity_until.get(state_key, 0.0)
        if now < immunity_until:
            remain = int(immunity_until - now)
            await giveup_cmd.finish(
                reply_prefix
                + MessageSegment.text(f"新题免死金牌生效中，{remain} 秒后才可投票放弃。")
            )

        voters = _giveup_votes.setdefault(state_key, set())
        if user_id in voters:
            await giveup_cmd.finish(
                reply_prefix + MessageSegment.text(f"你已经投过本题放弃票了。当前 {len(voters)}/{required_votes}。")
            )
        voters.add(user_id)
        if len(voters) < required_votes:
            await giveup_cmd.finish(
                reply_prefix
                + MessageSegment.text(f"已记录放弃票。当前 {len(voters)}/{required_votes}。")
            )

    # Serialize requests for the same difficulty so only one render runs.
    async with _busy_locks[lock_key]:
        _giveup_running.add(state_key)
        _giveup_votes[state_key] = set()
        try:
            old_problem = get_current_problem(difficulty_key, source=source)
            if old_problem is not None:
                await giveup_cmd.send(
                    reply_prefix
                    + MessageSegment.text(_format_giveup_message(old_problem, old_problem.ai_brief))
                )
            else:
                await giveup_cmd.send(reply_prefix + MessageSegment.text("当前没有可揭示的题目，将直接准备下一题。"))

            await giveup_cmd.send(
                reply_prefix + MessageSegment.text(f"正在准备 {source} {difficulty.display_name} 难度下一题，请稍候…")
            )

            try:
                problem = await advance_problem(difficulty_key, source=source)
            except Exception as exc:
                logger.exception("Failed to prepare random problem")
                await giveup_cmd.finish(f"随机题准备失败：{exc}")

            _giveup_votes[state_key] = set()
            _giveup_immunity_until[state_key] = time.time() + _GIVEUP_IMMUNITY_SECONDS
            await send_problem_image(bot, event, problem)
            await giveup_cmd.finish()
        finally:
            _giveup_running.discard(state_key)


@cur_cmd.handle()
async def handle_cur(bot: Bot, event: Event, args: Message = CommandArg()) -> None:
    if not is_superuser(event) and not algo_enabled_for_event(event):
        await cur_cmd.finish()

    source, difficulty_key, _ = parse_source_difficulty_args(args.extract_plain_text(), require_source=True)
    if source is None or difficulty_key is None:
        await cur_cmd.finish("用法：/cur <cf|at> <难度>\n\n" + difficulty_usage())

    problem = get_current_problem(difficulty_key, source=source)
    if problem is None:
        await cur_cmd.finish(
            f"当前没有 {source} {DIFFICULTIES_BY_SOURCE[source][difficulty_key].display_name} 难度题目缓存。"
            f"请先使用 /giveup {source} {difficulty_key}。"
        )

    await send_problem_image(bot, event, problem)
    await cur_cmd.finish()


def _reply_to_event(event: Event) -> Message:
    message_id = getattr(event, "message_id", None)
    if isinstance(event, MessageEvent) and isinstance(message_id, int):
        return Message(MessageSegment.reply(message_id))
    return Message()


def _problem_info(problem: RenderedProblem) -> dict[str, object]:
    return {
        "contest_id": problem.contest_id,
        "index": problem.index,
        "name": problem.original_name,
        "rating": problem.rating,
        "tags": problem.tags,
        "tutorial_url": problem.tutorial_url,
    }


def _format_giveup_message(problem: RenderedProblem, solution_brief: str) -> str:
    prefix = "CF" if problem.source == "cf" else "AT"
    problem_id = f"{problem.contest_id}{problem.index}" if problem.source == "cf" else problem.index
    return (
        "已放弃当前题目。\n"
        f"原题：{prefix}{problem_id} - {problem.original_name}\n"
        f"rating：{problem.rating}\n"
        f"链接：{problem.url}\n\n"
        f"简要题解：\n{solution_brief or '缓存题解为空。'}"
    )


async def advance_problem(difficulty_key: str, source: str = "cf") -> RenderedProblem:
    problem = await giveup_to_next(difficulty_key, source=source)
    warm_states_in_background(difficulty_key, exclude_keys={problem.key}, source=source)
    return problem


async def send_problem_image(
    bot: Bot,
    event: Event,
    problem: RenderedProblem,
) -> None:
    """Send a single merged image containing both statement and samples."""
    await bot.send(
        event,
        Message(
            MessageSegment.image(Path(problem.statement_image).resolve().as_uri())
        ),
    )
