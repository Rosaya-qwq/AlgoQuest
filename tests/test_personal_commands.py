import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.exception import FinishedException

from bot.services import stars
from bot.services.stars import ProblemId, list_stars, record_solution_message, solution_message_problem


@pytest.fixture
def plugins(monkeypatch, tmp_path):
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init(driver="~fastapi", log_level="WARNING")
    modules = SimpleNamespace(**{
        name: importlib.import_module("bot.plugins." + name)
        for name in ("stars", "emoji_reaction", "basic", "problem_random")
    })
    monkeypatch.setattr(stars, "STAR_DB_PATH", tmp_path / "stars.sqlite3")
    for name in ("stars", "emoji_reaction", "basic"):
        monkeypatch.setattr(getattr(modules, name), "is_superuser", lambda _: True)
    return modules


def capture_matcher(monkeypatch, matcher):
    messages = []

    async def send(message):
        messages.append(message)

    async def finish(message=None):
        if message is not None:
            messages.append(message)
        raise FinishedException

    monkeypatch.setattr(matcher, "send", send)
    monkeypatch.setattr(matcher, "finish", finish)
    return messages


def event(user=100, reply=None, message=None):
    return SimpleNamespace(user_id=user, message_id=999, reply=reply, message=message or Message())


def invoke(handler, *args):
    with pytest.raises(FinishedException):
        asyncio.run(handler(*args))


def test_emoji_quoted_image_renames_instead_of_reacting(plugins, monkeypatch):
    plugin = plugins.emoji_reaction
    capture_matcher(monkeypatch, plugin.emoji_cmd)
    reaction = AsyncMock()
    monkeypatch.setattr(plugin, "_set_msg_emoji_like", reaction)
    bot = SimpleNamespace(send=AsyncMock(), call_api=AsyncMock())
    reply = SimpleNamespace(message_id=123, message=Message(MessageSegment("image", {"url": "https://cdn.example/a.gif"})))
    invoke(plugin.handle_emoji, bot, event(reply=reply), Message("1"))
    output = bot.send.call_args.args[1]
    assert len(output) == 1 and output[0].type == "image"
    assert output[0].data["summary"] == "1" and output[0].data["sub_type"] == 1
    reaction.assert_not_called()
    bot.call_api.assert_not_called()


def test_emoji_plain_text_reply_keeps_original_reaction(plugins, monkeypatch):
    plugin = plugins.emoji_reaction
    capture_matcher(monkeypatch, plugin.emoji_cmd)
    reaction = AsyncMock(return_value=True)
    monkeypatch.setattr(plugin, "_set_msg_emoji_like", reaction)
    bot = SimpleNamespace(send=AsyncMock(), call_api=AsyncMock())
    reply = SimpleNamespace(message_id=123, message=Message("普通文字"))
    invoke(plugin.handle_emoji, bot, event(reply=reply), Message("368"))
    reaction.assert_awaited_once_with(bot, 123, "368")
    bot.send.assert_not_called()


def test_star_add_remove_and_query_are_per_user(plugins, monkeypatch):
    plugin = plugins.stars
    output = capture_matcher(monkeypatch, plugin.star_cmd)
    bot = SimpleNamespace(self_id="bot", call_api=AsyncMock())
    invoke(plugin.handle_star, bot, event(100), Message("CF2062A"))
    invoke(plugin.handle_star, bot, event(200), Message("+AT_arc017_1"))
    invoke(plugin.handle_star, bot, event(100), Message())
    assert "CF2062A" in output[-1] and "AT_arc017_1" not in output[-1]
    invoke(plugin.handle_star, bot, event(100), Message("-CF2062A"))
    assert list_stars("100") == []
    assert list_stars("200") == [ProblemId("at", "arc017_1")]
    bot.call_api.assert_not_called()


def test_star_quotes_image_solution_without_ocr_or_api_request(plugins, monkeypatch):
    plugin = plugins.stars
    capture_matcher(monkeypatch, plugin.star_cmd)
    record_solution_message("bot", 123, ProblemId("at", "arc017_1"))
    bot = SimpleNamespace(self_id="bot", call_api=AsyncMock())
    reply = SimpleNamespace(message_id=123, message=Message(MessageSegment.image("opaque-image")))
    invoke(plugin.handle_star, bot, event(reply=reply), Message())
    assert list_stars("100") == [ProblemId("at", "arc017_1")]
    bot.call_api.assert_not_called()
    invoke(plugin.handle_star, bot, event(reply=reply), Message("-"))
    assert not list_stars("100")


def test_star_fetches_quote_and_rejects_ambiguous_problem_ids(plugins, monkeypatch):
    plugin = plugins.stars
    output = capture_matcher(monkeypatch, plugin.star_cmd)
    bot = SimpleNamespace(self_id="bot", call_api=AsyncMock(return_value={"message": [
        {"type": "text", "data": {"text": "CF2062A 和 AT_arc017_1"}},
    ]}))
    quoted = event(message=Message([MessageSegment.reply(123), MessageSegment.text("/star")]))
    invoke(plugin.handle_star, bot, quoted, Message())
    assert "多个题号" in output[-1]
    assert list_stars("100") == []
    bot.call_api.assert_awaited_once_with("get_msg", message_id="123")


def test_solution_delivery_records_problem_without_storing_image_url(plugins, monkeypatch, tmp_path):
    from bot.services import solutions

    image = tmp_path / "solution.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(solutions, "render_solution_image", AsyncMock(return_value=image))
    bot = SimpleNamespace(self_id="bot", send=AsyncMock(return_value={"message_id": 123}))
    problem = SimpleNamespace(source="cf", key="2062A")
    asyncio.run(plugins.problem_random.send_solution_image(bot, event(), problem))
    assert solution_message_problem("bot", 123) == ProblemId("cf", "2062A")


def test_ping_image_send_failure_falls_back_to_pong(plugins, monkeypatch):
    plugin = plugins.basic
    output = capture_matcher(monkeypatch, plugin.ping_cmd)
    monkeypatch.setattr(plugin, "ping_image", lambda: MessageSegment("image", {"file": "file:///source/ping.png", "sub_type": 1}))
    monkeypatch.setattr(plugin.ping_cmd, "send", AsyncMock(side_effect=RuntimeError("unavailable")))
    invoke(plugin.handle_ping, event())
    assert output == ["pong"]
