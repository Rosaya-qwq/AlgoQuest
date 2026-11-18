import asyncio
from types import SimpleNamespace

import httpx

from bot.services import solutions
from bot.services import html_render
from bot.services.html_render import build_html
from bot.services.tutorials import TutorialReference


def test_mathjax_falls_back_to_second_mirror_then_works_offline(monkeypatch, tmp_path):
    path = tmp_path / "mathjax.js"
    monkeypatch.setattr(html_render, "MATHJAX_CACHE_PATH", path)
    calls = []
    script = "/* MathJax */\n" + "/**/" * 30000

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, text=script)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(html_render.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    assert asyncio.run(html_render._mathjax_bundle()) == script
    assert path.read_text() == script
    assert asyncio.run(html_render._mathjax_bundle()) == script
    assert len(calls) == 2


def test_bold_chinese_explanations_keep_inner_math_delimiters():
    html = build_html(title="题解", blocks=[{
        "type": "paragraph", "text": r"**大小为 $s$ 的环，可取 $\lfloor s/2\rfloor$ 个点。**",
    }])
    assert r"<strong>大小为 $s$ 的环，可取 $\lfloor s/2\rfloor$ 个点。</strong>" in html


def test_solution_preserves_illustration_order_and_note_images():
    uri = "data:image/png;base64,AAAA"
    text = '说明 $x^2$。\n\n![构造](https://cdn.example/a.png)\n\n后续证明。\n\n:::note\n![补充](https://cdn.example/a.png)\n:::'
    blocks = solutions._solution_blocks(text, {"https://cdn.example/a.png": uri})
    assert [b["type"] for b in blocks] == ["paragraph", "image", "paragraph", "note"]
    assert blocks[1]["data_uri"] == uri
    assert blocks[-1]["blocks"][0]["data_uri"] == uri


def test_solution_image_retries_missing_assets_and_reuses_complete_render(monkeypatch, tmp_path):
    monkeypatch.setattr(solutions, "SOLUTION_DIR", tmp_path)
    problem = SimpleNamespace(
        source="cf", key="1A", original_name="Theatre Square", difficulty="easy", rating=1000,
        ai_brief="关键观察 $a+b$。\n\n![构造](https://cdn.example/a.png)\n\n证明思路。",
    )
    reference = TutorialReference(
        content="![构造](https://cdn.example/a.png)\n![附图](https://cdn.example/b.png)",
        url="https://www.luogu.com.cn/article/example",
    )
    downloads, rendered = [], []

    async def ref(_):
        return reference

    async def image(client, url):
        downloads.append(url)
        if len(downloads) <= 2:
            return None
        return "data:image/png;base64," + ("AAAA" if url.endswith("a.png") else "BBBB")

    async def render(html, path):
        rendered.append(html)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PNG")

    monkeypatch.setattr(solutions, "problem_reference", ref)
    monkeypatch.setattr(solutions, "cache_image", image)
    monkeypatch.setattr(solutions, "render_html_to_png", render)

    async def run():
        partial = await solutions.render_solution_image(problem)
        complete = await solutions.render_solution_image(problem)
        reused = await solutions.render_solution_image(problem)
        assert partial != complete == reused

    asyncio.run(run())
    assert len(rendered) == 2
    assert "配图暂不可用" in rendered[0]
    assert rendered[1].count('<img src="data:image/png;base64,') == 2
    assert '<img src="https://' not in rendered[1]
    assert "参考题解配图" in rendered[1]
    assert rendered[1].index("AAAA") < rendered[1].index("证明思路") < rendered[1].index("BBBB")


def test_reference_without_generated_brief_is_rendered_with_original_image_positions(monkeypatch, tmp_path):
    monkeypatch.setattr(solutions, "SOLUTION_DIR", tmp_path)
    problem = SimpleNamespace(source="at", key="arc017_1", original_name="素数", difficulty="easy", rating=1000, ai_brief="")
    rendered = []

    async def ref(_):
        return TutorialReference(content="先说明。\n\n![图](https://cdn.example/a.png)\n\n再证明。", url="https://www.luogu.com.cn/article/example")

    async def image(*_):
        return "data:image/png;base64,AAAA"

    async def render(html, path):
        rendered.append(html)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PNG")

    monkeypatch.setattr(solutions, "problem_reference", ref)
    monkeypatch.setattr(solutions, "cache_image", image)
    monkeypatch.setattr(solutions, "render_html_to_png", render)
    asyncio.run(solutions.render_solution_image(problem))
    assert rendered[0].index("先说明") < rendered[0].index("AAAA") < rendered[0].index("再证明")
