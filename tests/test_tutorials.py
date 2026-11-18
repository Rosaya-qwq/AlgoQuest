import asyncio
import io
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from bot.services import tutorials


def page(data):
    return '<script id="lentille-context" type="application/json">' + json.dumps({"data": data}) + '</script>'


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(tutorials, "TUTORIAL_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tutorials, "IMAGE_CACHE_DIR", tmp_path / "images")
    monkeypatch.setattr(tutorials, "_locks", {})
    monkeypatch.setattr(tutorials, "_retry_after", {})
    monkeypatch.setenv("LUOGU_COOKIE", "_uid=42; __client_id=test; C3VK=expired")
    monkeypatch.setenv("LUOGU_SOLUTIONS_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_HTTP_PROXY", "")


def test_time_last_pagination_full_article_and_offline_cache(monkeypatch, tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "www.luogu.com.cn"
        assert "_uid=42" in request.headers.get("cookie", "")
        if len(requests) == 1:
            return httpx.Response(302, headers={
                "location": str(request.url), "set-cookie": "C3VK=; Max-Age=0; Path=/",
            })
        assert "C3VK" not in request.headers.get("cookie", "")
        if request.url.path.startswith("/article/"):
            assert request.url.path == "/article/last"
            return httpx.Response(200, text=page({"article": {
                "title": "Full tutorial", "content": "构造与证明\n![图](https://cdn.example/diagram.png)",
            }}))
        assert request.url.path == "/problem/solution/AT_arc017_1"
        assert request.url.params["orderBy"] == "time"
        items = [{"lid": "first", "content": "wrong"}]
        if request.url.params.get("page") == "3":
            items = [{"lid": "penultimate", "content": "wrong"},
                     {"lid": "last", "content": "truncated", "contentFull": False}]
        return httpx.Response(200, text=page({
            "problem": {"pid": "AT_arc017_1"},
            "solutions": {"count": 5, "perPage": 2, "result": items},
        }))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(tutorials.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    problem = SimpleNamespace(source="at", key="arc017_1")
    refs = asyncio.run(tutorials.luogu_references(problem))
    assert len(refs) == 1 and "构造与证明" in refs[0].content
    assert refs[0].url.endswith("/last")
    assert len(requests) == 4
    saved = (tmp_path / "luogu/AT_arc017_1.json").read_text()
    assert "_uid" not in saved and "__client_id" not in saved
    monkeypatch.setenv("LUOGU_COOKIE", "")
    assert asyncio.run(tutorials.luogu_references(problem)) == refs
    assert len(requests) == 4


def test_expired_login_uses_stale_cache_and_does_not_overwrite(monkeypatch, tmp_path):
    directory = tmp_path / "luogu"
    directory.mkdir()
    path = directory / "CF1A.json"
    path.write_text(json.dumps({
        "pid": "CF1A", "selection": "time-last-v1", "fetched_at": 0,
        "references": [{"content": "old good tutorial", "url": "https://www.luogu.com.cn/article/old", "title": "old"}],
    }))
    before = path.read_bytes()
    real_client = httpx.AsyncClient
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401)

    monkeypatch.setattr(tutorials.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    problem = SimpleNamespace(source="cf", key="1A")
    assert asyncio.run(tutorials.luogu_references(problem))[0].content == "old good tutorial"
    assert asyncio.run(tutorials.luogu_references(problem))[0].content == "old good tutorial"
    assert len(calls) == 1 and path.read_bytes() == before


def test_no_published_solutions_is_normal_and_retries_later(monkeypatch, tmp_path):
    calls, warnings, information = [], [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=page({
            "problem": {"pid": "CF2062A"},
            "solutions": {"count": 0, "perPage": 10, "result": []},
        }))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(tutorials.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    monkeypatch.setattr(tutorials.logger, "warning", warnings.append)
    monkeypatch.setattr(tutorials.logger, "info", information.append)
    problem = SimpleNamespace(source="cf", key="2062A")
    assert not asyncio.run(tutorials.luogu_references(problem))
    assert not asyncio.run(tutorials.luogu_references(problem))
    assert len(calls) == 1
    assert not warnings
    assert "No Luogu tutorials published for CF2062A" in information[0]
    assert not list(tmp_path.rglob("*.json"))


def test_wrong_problem_and_external_redirect_are_rejected(monkeypatch, tmp_path):
    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("CF1A"):
            return httpx.Response(200, text=page({
                "problem": {"pid": "CF2B"},
                "solutions": {"result": [{"lid": "bad", "content": "wrong problem"}]},
            }))
        return httpx.Response(302, headers={"location": "https://outside.example/"})

    monkeypatch.setattr(tutorials.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    assert not asyncio.run(tutorials.luogu_references(SimpleNamespace(source="cf", key="1A")))
    assert not asyncio.run(tutorials.luogu_references(SimpleNamespace(source="cf", key="2B")))
    assert len(requests) == 2
    assert not list(tmp_path.rglob("*.json"))


def test_image_is_downloaded_without_credentials_and_reused(tmp_path):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), "blue").save(buffer, format="JPEG")
    calls = []

    def handler(request):
        assert "cookie" not in request.headers and "authorization" not in request.headers
        calls.append(request)
        return httpx.Response(200, content=buffer.getvalue(), headers={"content-type": "image/jpeg"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            first = await tutorials.cache_image(client, "https://cdn.example/diagram")
            second = await tutorials.cache_image(client, "https://cdn.example/diagram")
            assert first == second and first.startswith("data:image/png;base64,")

    asyncio.run(run())
    assert len(calls) == 1


def test_broken_image_does_not_poison_cache():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="<html>login required</html>")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await tutorials.cache_image(client, "https://cdn.example/image") is None
            assert await tutorials.cache_image(client, "https://cdn.example/image") is None

    asyncio.run(run())
    assert len(calls) == 2


def test_image_urls_resolve_and_code_examples_are_ignored():
    text = '![图](/img.png)\n<img src="//cdn.example/a.svg" alt="示意图">\n```md\n![example](https://bad.example/x)\n```'
    assert tutorials.image_links(text, "https://www.luogu.com.cn/article/a") == [
        ("https://www.luogu.com.cn/img.png", "图"), ("https://cdn.example/a.svg", "示意图"),
    ]
