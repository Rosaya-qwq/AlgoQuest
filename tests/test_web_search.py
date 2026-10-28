import asyncio
import json

import httpx
import pytest

from bot.services import web_search


def _run_search(monkeypatch, replies, *, query="算法竞赛", images=()):
    calls = []
    sequence = iter(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((str(request.url), body))
        return httpx.Response(200, json=next(sequence))

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return calls, asyncio.run(web_search.search_web(query, images))


def _chat(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_search_uses_fresh_messages_and_reviews_answer(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            _chat("算法竞赛 图片内容"),
            _chat('{"allowed": true}'),
            {"results": [{"title": "教程", "url": "https://example.com/a", "summary": "排序教程", "content": ""}]},
            _chat("先排序后扫描。"),
            _chat('{"allowed": true}'),
        ],
        images=("https://example.com/input.png",),
    )

    assert "先排序后扫描。" in reply.text
    assert "https://example.com/a" in reply.text
    assert reply.image_urls == ()
    assert len(calls) == 6
    assert calls[3][0].endswith("/v1/tools/search")
    assert calls[3][1]["query"] == "算法竞赛 图片内容"
    assert calls[3][1]["need_content"] is True
    for url, body in (calls[0], calls[1], calls[2], calls[4], calls[5]):
        assert url.endswith("/chat/completions")
        assert body["model"] == "deepseek-flash"
        assert [message["role"] for message in body["messages"]] == ["system", "user"]
    user_parts = calls[4][1]["messages"][1]["content"]
    assert user_parts[1]["image_url"]["url"] == "https://example.com/input.png"
    assert "算法竞赛" in calls[1][1]["messages"][1]["content"][0]["text"]


def test_image_only_search_derives_query(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            _chat("图片里的花"),
            _chat('{"allowed": true}'),
            {"results": []},
        ],
        query="",
        images=("https://example.com/input.png",),
    )
    assert reply.text == "没有找到相关网页。"
    assert calls[3][1]["query"] == "图片里的花"


def test_search_rejects_query_before_web_request(monkeypatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=_chat('{"allowed": false}'))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(web_search.SearchRejected):
        asyncio.run(web_search.search_web("政治相关内容"))

    assert len(calls) == 1
    assert calls[0].endswith("/chat/completions")


def test_search_rejects_unsafe_output_and_keeps_images_private(monkeypatch) -> None:
    replies = [
        _chat('{"allowed": true}'),
        {"results": [{
            "title": "示例",
            "url": "https://example.com/a",
            "summary": "示例图",
            "content": "![图](https://example.com/image.png)",
        }]},
        _chat("查看 [图片1]。"),
        _chat('{"allowed": false}'),
    ]
    calls = []
    sequence = iter(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=next(sequence))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(web_search.SearchRejected):
        asyncio.run(web_search.search_web("示例图片"))

    assert len(calls) == 4
    assert calls[3]["messages"][1]["content"][1]["image_url"]["url"] == "https://example.com/image.png"


def test_search_returns_only_referenced_images(monkeypatch) -> None:
    _calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            {"results": [{
                "title": "示例",
                "url": "https://example.com/a",
                "summary": "示例",
                "content": "![一](https://example.com/1.png) ![二](https://example.com/2.png)",
            }]},
            _chat("请看 [图片2]。"),
            _chat('{"allowed": true}'),
        ],
    )
    assert reply.image_urls == ("https://example.com/2.png",)
