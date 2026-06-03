from __future__ import annotations

import asyncio

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from bot.plugins.problem_random import advance_problem, send_problem_image
from bot.services.problem_random import (
    DIFFICULTIES_BY_SOURCE,
    difficulty_usage,
    get_current_problem,
    read_problem_markdown,
    read_problem_tutorial,
)
from bot.services.permissions import get_event_user_id, is_group_admin_or_superuser, is_superuser
from bot.services.submission import (
    apply_rating_update,
    format_review_message,
    parse_submit_args,
    problem_snapshot_key,
    review_submission,
)


__plugin_meta__ = PluginMetadata(
    name="题解提交评审",
    description="使用 DeepSeek 根据当前题面和用户题解描述做思路判题，并更新本地 rating。",
    usage="/submit cf easy 我的做法是...",
)


submit_cmd = on_command("submit", aliases={"提交", "判题"}, priority=5, block=True)
pass_cmd = on_command("pass", aliases={"通过"}, priority=5, block=True)

_QUEUE_KEYS = [
    f"{source}:{key}"
    for source, difficulties in DIFFICULTIES_BY_SOURCE.items()
    for key in difficulties
]
_submit_counters: dict[str, int] = {key: 0 for key in _QUEUE_KEYS}
_submit_queues: dict[str, list[int]] = {key: [] for key in _QUEUE_KEYS}
_submit_conditions: dict[str, asyncio.Condition] = {key: asyncio.Condition() for key in _QUEUE_KEYS}
_first_blood_snapshot_keys: set[str] = set()


@submit_cmd.handle()
async def handle_submit(bot: Bot, event: Event, args: Message = CommandArg()) -> None:
    reply_prefix = _reply_to_event(event)
    user_id = _event_user_id(event)
    if user_id is None:
        await submit_cmd.finish("无法识别提交用户。")

    source, difficulty_key, solution = parse_submit_args(args.extract_plain_text())
    if source is None or difficulty_key is None:
        await submit_cmd.finish(_submit_usage())
    if not solution:
        await submit_cmd.finish("请在难度后写上你的题解或算法描述。\n\n" + _submit_usage())

    queue_key = _queue_key(source, difficulty_key)
    sequence = await _reserve_submit_turn(queue_key)
    next_problem = None
    refresh_error: Exception | None = None
    try:
        problem = get_current_problem(difficulty_key, source=source)
        if problem is None:
            await submit_cmd.finish(
                f"当前没有 {source} {DIFFICULTIES_BY_SOURCE[source][difficulty_key].display_name} 难度题目缓存。"
                f"请先使用 /giveup {source} {difficulty_key} 获取题目。"
            )

        problem_statement = read_problem_markdown(problem)
        if not problem_statement.strip():
            await submit_cmd.finish("当前题目的文本缓存不存在，无法进行 AI 评审。请重新 /giveup 获取题目。")

        await submit_cmd.send(reply_prefix + MessageSegment.text("已加入提交队列，将严格按提交顺序评审。"))
        await _wait_submit_turn(queue_key, sequence)
        await submit_cmd.send(
            reply_prefix
            + MessageSegment.text("正在评审你的本次提交：会检查样例、额外构造两组小数据、证明和复杂度，请稍候。")
        )
        try:
            review = await review_submission(
                problem=problem,
                problem_statement=problem_statement,
                user_solution=solution,
                tutorial_text=read_problem_tutorial(problem),
                tutorial_url=problem.tutorial_url,
                difficulty_key=difficulty_key,
            )
            snapshot_key = problem_snapshot_key(difficulty_key, problem, source=source)
            rating_eligible = snapshot_key not in _first_blood_snapshot_keys
            no_rating_reason = ""
            if not rating_eligible:
                no_rating_reason = "本题一血已产生；本次只返回判题结果，不增加 rating。"
            rating_update = apply_rating_update(
                user_id=user_id,
                source=source,
                difficulty_key=difficulty_key,
                problem=problem,
                review=review,
                rating_eligible=rating_eligible,
                no_rating_reason=no_rating_reason,
            )
            if review.accepted and rating_eligible:
                _first_blood_snapshot_keys.add(snapshot_key)
                try:
                    next_problem = await advance_problem(difficulty_key, source=source)
                except Exception as exc:
                    refresh_error = exc
                    logger.exception("Failed to refresh next problem after first blood submit")
        except Exception as exc:
            logger.exception("Failed to review submission")
            await submit_cmd.finish(f"提交评审失败：{exc}")

        await submit_cmd.send(
            reply_prefix
            + MessageSegment.text(
                format_review_message(
                    difficulty_key=difficulty_key,
                    problem=problem,
                    review=review,
                    rating_update=rating_update,
                )
                + (_solution_brief_block(problem) if review.accepted else "")
            )
        )

        if refresh_error is not None:
            await submit_cmd.finish(f"本题已通过，但刷新下一题失败：{refresh_error}")

        if next_problem is not None:
            try:
                await submit_cmd.send(reply_prefix + MessageSegment.text("已刷新下一题："))
                await send_problem_image(bot, event, next_problem)
            except Exception as exc:
                logger.exception("Failed to send next problem image after first blood submit")
                await submit_cmd.finish(f"本题已通过，但发送下一题图片失败：{exc}")
    finally:
        await _leave_submit_turn(queue_key, sequence)

    await submit_cmd.finish()


@pass_cmd.handle()
async def handle_pass(bot: Bot, event: Event, args: Message = CommandArg()) -> None:
    source, difficulty_key, extra_arg = parse_submit_args(args.extract_plain_text())
    if source is None or difficulty_key is None:
        await pass_cmd.finish("用法：回复用户提交消息，发送 /pass <cf|at> <难度>\n\n" + difficulty_usage("/pass"))
    if extra_arg.strip():
        await pass_cmd.finish("用法：回复用户提交消息，发送 /pass <cf|at> <难度>。不能手动输入 uid。")
    if not _has_reply(event):
        await pass_cmd.finish("请回复用户提交消息使用 /pass，不能直接输入 uid 通过。")

    problem = get_current_problem(difficulty_key, source=source)
    if problem is None:
        await pass_cmd.finish(f"当前没有 {source} {difficulty_key} 题目缓存。")

    if not await is_group_admin_or_superuser(bot, event):
        await pass_cmd.finish("只有管理员可以 /pass。")

    snapshot_key = problem_snapshot_key(difficulty_key, problem, source=source)
    if _is_reply_to_bot(bot, event):
        await pass_cmd.finish("不能回复机器人消息使用 /pass；请回复用户提交消息。")

    user_id = _extract_reply_user_id(event)
    if user_id is None:
        await pass_cmd.finish("无法识别被回复消息的用户。")
    if user_id == str(bot.self_id):
        await pass_cmd.finish("不能给机器人账号执行 /pass。")

    if snapshot_key in _first_blood_snapshot_keys:
        await pass_cmd.finish("本题一血已产生，/pass 无效。")

    review = _forced_accept_review()
    rating_update = apply_rating_update(
        user_id=user_id,
        source=source,
        difficulty_key=difficulty_key,
        problem=problem,
        review=review,
        rating_eligible=True,
    )
    _first_blood_snapshot_keys.add(snapshot_key)
    try:
        next_problem = await advance_problem(difficulty_key, source=source)
    except Exception as exc:
        logger.exception("Failed to refresh next problem after /pass")
        await pass_cmd.finish(f"已强制通过，但刷新下一题失败：{exc}")

    await pass_cmd.send(
        _reply_to_event(event)
        + MessageSegment.text(
            format_review_message(
                difficulty_key=difficulty_key,
                problem=problem,
                review=review,
                rating_update=rating_update,
            )
            + _solution_brief_block(problem)
        )
    )
    await pass_cmd.send(_reply_to_event(event) + MessageSegment.text("已刷新下一题："))
    await send_problem_image(bot, event, next_problem)
    await pass_cmd.finish()


async def _reserve_submit_turn(queue_key: str) -> int:
    condition = _submit_conditions[queue_key]
    async with condition:
        _submit_counters[queue_key] += 1
        sequence = _submit_counters[queue_key]
        _submit_queues[queue_key].append(sequence)
        condition.notify_all()
        return sequence


async def _wait_submit_turn(queue_key: str, sequence: int) -> None:
    condition = _submit_conditions[queue_key]
    async with condition:
        while not _submit_queues[queue_key] or _submit_queues[queue_key][0] != sequence:
            await condition.wait()


async def _leave_submit_turn(queue_key: str, sequence: int) -> None:
    condition = _submit_conditions[queue_key]
    async with condition:
        queue = _submit_queues[queue_key]
        if queue and queue[0] == sequence:
            queue.pop(0)
        else:
            try:
                queue.remove(sequence)
            except ValueError:
                pass
        condition.notify_all()


def _queue_key(source: str, difficulty_key: str) -> str:
    return f"{source}:{difficulty_key}"


def _solution_brief_block(problem) -> str:
    return f"\n\n简要题解：\n{problem.ai_brief or '缓存题解为空。'}"


def _forced_accept_review():
    from bot.services.submission import SubmissionReview

    return SubmissionReview(
        verdict="ACCEPTED",
        score=1.0,
        confidence=1.0,
        sample_simulation="管理员强制通过。",
        extra_tests=[],
        proof_check="管理员强制通过。",
        complexity_check="管理员强制通过。",
        issues=[],
        suggestions=[],
        summary="管理员强制通过。",
    )


def _extract_reply_user_id(event: Event) -> str | None:
    message = getattr(event, "reply", None)
    sender = getattr(message, "sender", None)
    user_id = getattr(sender, "user_id", None)
    return str(user_id) if user_id is not None else None


def _has_reply(event: Event) -> bool:
    return getattr(event, "reply", None) is not None


def _is_reply_to_bot(bot: Bot, event: Event) -> bool:
    reply_user_id = _extract_reply_user_id(event)
    return reply_user_id is not None and reply_user_id == str(bot.self_id)

def _event_user_id(event: Event) -> str | None:
    if isinstance(event, MessageEvent):
        return str(event.user_id)
    user_id = getattr(event, "user_id", None)
    return str(user_id) if user_id is not None else None


def _reply_to_event(event: Event) -> Message:
    message_id = getattr(event, "message_id", None)
    if isinstance(message_id, int):
        return Message(MessageSegment.reply(message_id))
    return Message()


def _submit_usage() -> str:
    return (
        "用法：/submit <cf|at> <难度> <题解描述>\n"
        "例如：/submit cf easy 我先排序，然后用双指针维护...\n\n"
        + difficulty_usage()
    )
