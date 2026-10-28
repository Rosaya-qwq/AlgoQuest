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
    assert "https://example.com/a" not in reply.text
    assert reply.image_urls == ()
    assert len(calls) == 6
    assert calls[3][0].endswith("/v1/tools/search")
    assert calls[3][1]["query"] == "算法竞赛 图片内容"
    assert calls[3][1]["count"] == 8
    assert calls[3][1]["need_content"] is True
    for url, body in (calls[0], calls[1], calls[2], calls[4], calls[5]):
        assert url.endswith("/chat/completions")
        assert body["model"] == "deepseek-flash"
        assert [message["role"] for message in body["messages"]] == ["system", "user"]
    user_parts = calls[4][1]["messages"][1]["content"]
    assert user_parts[1]["image_url"]["url"] == "https://example.com/input.png"
    assert user_parts[1]["image_url"]["detail"] == "original"
    assert calls[4][1]["thinking"]["type"] == "enabled"
    assert calls[4][1]["reasoning_effort"] == "high"
    assert calls[4][1]["max_tokens"] == 65536
    assert "用户原始问题：算法竞赛" in user_parts[0]["text"]
    assert "算法竞赛" in calls[1][1]["messages"][1]["content"][0]["text"]


def test_image_only_search_derives_query(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            _chat("图片里的花"),
            _chat('{"allowed": true}'),
            {"results": []},
            _chat("这是一朵花。"),
            _chat('{"allowed": true}'),
        ],
        query="",
        images=("https://example.com/input.png",),
    )
    assert reply.text == "这是一朵花。"
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
    assert calls[3]["messages"][1]["content"] == "查看 [图片1]。"


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
            _chat('{"allowed": true}'),
        ],
    )
    assert reply.image_urls == ("https://example.com/2.png",)


def test_image_search_prioritizes_images_and_skips_unsafe_candidate(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            {"results": [{
                "title": "角色图库",
                "url": "https://example.com/gallery",
                "summary": "角色插画",
                "content": "![角色](https://example.com/character.png)",
            }]},
            _chat("找到一张角色插画 [图片1]。"),
            _chat('{"allowed": true}'),
            _chat('{"allowed": false}'),
        ],
        query="帮我找一张海泽莉塔的图片",
    )

    assert "图片" in reply.text or "插画" in reply.text
    assert reply.image_urls == ()
    assert "-site:github.com" in calls[1][1]["query"]
    assert calls[4][1]["messages"][1]["content"][1]["image_url"]["url"] == "https://example.com/character.png"


def test_image_search_fetches_page_when_search_has_no_image(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            {"results": [{"title": "图库", "url": "https://example.com/gallery", "summary": "角色图库", "content": ""}]},
            {"title": "图库", "content": "![角色](https://example.com/character.png)"},
            _chat("这张图符合要求 [图片1]。"),
            _chat('{"allowed": true}'),
            _chat('{"allowed": true}'),
        ],
        query="帮我找一张鲸鱼娘的图片",
    )

    assert calls[2][0].endswith("/v1/tools/fetch")
    assert calls[2][1]["url"] == "https://example.com/gallery"
    assert reply.image_urls == ("https://example.com/character.png",)


def test_moegirl_file_page_uses_og_image(monkeypatch) -> None:
    calls = []
    replies = iter([
        _chat('{"allowed": true}'),
        {"results": [{
            "title": "白圣女与黑牧师 海泽莉塔.jpg",
            "url": "https://commons.moegirl.org.cn/File:Hazelita.jpg",
            "summary": "角色图片文件页",
            "content": "",
        }]},
        _chat("找到角色图片 [图片1]。"),
        _chat('{"allowed": true}'),
        _chat('{"allowed": true}'),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.method == "GET":
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=(
                '<html><head><meta property="og:image" '
                'content="https://storage.moegirl.org.cn/moegirl/commons/e/ea/Hazelita.jpg"></head></html>'
            ))
        return httpx.Response(200, json=next(replies))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    reply = asyncio.run(web_search.search_web("帮我找一张海泽莉塔的图片"))

    assert "https://commons.moegirl.org.cn/File:Hazelita.jpg" in calls
    assert reply.image_urls == ("https://storage.moegirl.org.cn/moegirl/commons/e/ea/Hazelita.jpg",)


def test_image_search_retries_with_file_query_when_first_search_has_only_pages(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            {"results": [{"title": "截图专栏", "url": "https://example.com/article"}]},
            {"content": "只有文章，没有图片"},
            {"results": [{
                "title": "角色原图", "url": "https://example.com/gallery",
                "content": "![角色](https://example.com/character.jpg)",
            }]},
            _chat("角色图片 [图片1]。"),
            _chat('{"allowed": true}'),
            _chat('{"allowed": true}'),
        ],
        query="帮我找一张角色图片",
    )
    assert calls[3][0].endswith("/v1/tools/search")
    assert "原图 图片文件" in calls[3][1]["query"]
    assert reply.image_urls == ("https://example.com/character.jpg",)


def test_image_search_retries_even_when_first_search_is_empty(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            {"results": []},
            {"results": [{"url": "https://example.com/character.jpg"}]},
            _chat("图片 [图片1]。"),
            _chat('{"allowed": true}'),
            _chat('{"allowed": true}'),
        ],
        query="找张角色图片",
    )
    assert calls[2][0].endswith("/v1/tools/search")
    assert reply.image_urls == ("https://example.com/character.jpg",)


def test_image_selection_fallback_when_answer_fails_to_reference_candidates(monkeypatch) -> None:
    calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            {"results": [{"url": "https://example.com/character.jpg"}]},
            _chat("我只有网页，没有可展示的图片。"),
            _chat('{"selected": [true, "1", -1, 1, 9]}'),
            _chat('{"allowed": true}'),
            _chat('{"allowed": true}'),
        ],
        query="找一张角色图片",
    )
    assert reply.image_urls == ("https://example.com/character.jpg",)
    assert "我只有网页" not in reply.text
    assert "[图片1]" in reply.text
    assert calls[3][1]["messages"][1]["content"][1]["image_url"]["url"] == reply.image_urls[0]


def test_image_selection_does_not_send_unrelated_candidates(monkeypatch) -> None:
    _calls, reply = _run_search(
        monkeypatch,
        [
            _chat('{"allowed": true}'),
            {"results": [{"url": "https://example.com/unrelated.jpg"}]},
            _chat("这张候选不是用户要的角色。"),
            _chat('{"selected": []}'),
            _chat('{"allowed": true}'),
        ],
        query="找一张角色图片",
    )
    assert reply.image_urls == ()


def test_file_history_preview_loads_normal_file_page_and_validates_redirects() -> None:
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            assert "action=" not in str(request.url)
            assert "oldid=" not in str(request.url)
            return httpx.Response(302, headers={"location": "/File:Character.jpg"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=(
            '<meta property="og:image" content="https://storage.moegirl.org.cn/character.jpg">'
        ))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await web_search._page_preview_image(
                client, "https://commons.moegirl.org.cn/index.php?title=File:Character.jpg&action=history&oldid=10",
            )

    assert asyncio.run(run()) == "https://storage.moegirl.org.cn/character.jpg"
    assert len(calls) == 2


def test_preview_does_not_follow_untrusted_redirect() -> None:
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await web_search._page_preview_image(client, "https://commons.moegirl.org.cn/File:Character.jpg")

    assert asyncio.run(run()) is None
    assert len(calls) == 1


def test_preview_scans_beyond_first_five_search_results(monkeypatch) -> None:
    visited = []

    async def preview(client, url):
        visited.append(url)
        return "https://example.com/character.jpg" if url.endswith("/6") else None

    monkeypatch.setattr(web_search, "_page_preview_image", preview)

    async def run():
        async with httpx.AsyncClient() as client:
            return await web_search._find_page_images(
                client, "https://api.deepseek.com", {}, [{"url": f"https://example.com/{i}"} for i in range(8)],
            )

    assert asyncio.run(run()) == ["https://example.com/character.jpg"]
    assert len(visited) == 8


def test_truncated_answer_retries_once_with_larger_budget(monkeypatch) -> None:
    calls = []
    replies = iter([
        _chat('{"allowed": true}'),
        {"results": [{"title": "题解", "url": "https://example.com/a", "summary": "相关资料"}]},
        {"choices": [{"finish_reason": "length", "message": {"content": ""}}]},
        _chat("完整解题思路。"),
        _chat('{"allowed": true}'),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=next(replies))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    reply = asyncio.run(web_search.search_web("这题怎么做"))

    assert reply.text == "完整解题思路。"
    assert calls[2]["max_tokens"] == 65536
    assert calls[3]["max_tokens"] == 131072


def test_problem_screenshot_is_not_treated_as_picture_request() -> None:
    assert not web_search._wants_images("帮我看这张图片里的题怎么做")
    assert web_search._wants_images("帮我找一张鲸鱼娘的图片")


def test_chat_400_reports_stage_and_redacts_image_url(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {
            "message": "Failed to fetch https://example.com/private?token=secret"
        }})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(RuntimeError, match="DeepSeek 内容审查失败 \\(HTTP 400\\)") as exc_info:
        asyncio.run(web_search.search_web("搜索这张图", ("https://example.com/input.png",)))

    assert "Failed to fetch" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)
