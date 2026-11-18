"""Render readable solution cards, embedding cached tutorial illustrations."""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Any

import httpx

from bot.services.deepseek import _parse_markdown_blocks, generate_solution_brief
from bot.services.html_render import build_html, render_html_to_png
from bot.services.paths import runtime_data_dir
from bot.services.tutorials import (
    _IMAGE_RE, _number, cache_image, image_links, problem_reference,
)

SOLUTION_DIR = runtime_data_dir() / "solutions"
SOLUTION_RENDER_VERSION = 2
_locks: dict[str, asyncio.Lock] = {}


def _solution_blocks(
    text: str, assets: dict[str, str | None], *, base_url: str = "",
) -> list[dict[str, Any]]:
    """Keep illustration positions, skipping images inside fenced code."""
    return _solution_blocks_from_blocks(_parse_markdown_blocks(text), assets, base_url)


def _solution_blocks_from_blocks(blocks, assets, base_url):
    output = []
    for block in blocks:
        if block["type"] == "note":
            output.append({**block, "blocks": _solution_blocks_from_blocks(block["blocks"], assets, base_url)})
        elif block["type"] == "pre":
            output.append(block)
        else:
            output.extend(_split_illustrations(block, assets, base_url))
    return output


def _split_illustrations(block, assets, base_url):
    text = block.get("text", "")
    result = []
    previous = 0
    for match in _IMAGE_RE.finditer(text):
        prefix = text[previous:match.start()].strip()
        if prefix:
            result.append({**block, "text": prefix})
        links = image_links(match.group(0), base_url)
        url, alt = links[0] if links else ("", "参考题解配图")
        data_uri = assets.get(url)
        if data_uri:
            result.append({"type": "image", "data_uri": data_uri, "text": alt})
        else:
            result.append({"type": "paragraph", "text": f"［配图暂不可用：{alt}］"})
        previous = match.end()
    suffix = text[previous:].strip()
    if suffix or not result:
        result.append({**block, "text": suffix})
    return result


async def render_solution_image(problem: Any) -> Path:
    key = f"{problem.source}-{problem.key}"
    async with _locks.setdefault(key, asyncio.Lock()):
        reference = await problem_reference(problem)
        text = (problem.ai_brief or "").strip()
        if not text or text.startswith(("简要题解生成失败", "未配置 DEEPSEEK_API_KEY")):
            if reference.content.strip():
                # Keep the selected reference's prose and illustration positions intact.
                text = reference.content
            else:
                text = await generate_solution_brief(
                    {"source": problem.source, "contest_id": problem.contest_id,
                     "index": problem.index, "name": problem.original_name,
                     "rating": problem.rating, "tags": problem.tags},
                    problem.statement_text, difficulty_key=problem.difficulty,
                )
        solution_links = image_links(text, reference.url)
        reference_links = image_links(reference.content, reference.url)
        links = list(dict.fromkeys(solution_links + reference_links))
        assets = {}
        async with httpx.AsyncClient(timeout=_number("TUTORIAL_IMAGE_TIMEOUT_SECONDS", 30)) as client:
            for url, _ in links:
                if url not in assets:
                    assets[url] = await cache_image(client, url)
        blocks = _solution_blocks(text, assets, base_url=reference.url)
        used = {url for url, _ in solution_links}
        appendix = [(url, alt) for url, alt in reference_links if url not in used]
        if appendix:
            blocks.append({"type": "heading", "text": "参考题解配图"})
            for index, (url, alt) in enumerate(appendix, 1):
                blocks.append({"type": "paragraph", "text": f"图 {index}：{alt}"})
                if assets.get(url):
                    blocks.append({"type": "image", "data_uri": assets[url], "text": alt})
                else:
                    blocks.append({"type": "paragraph", "text": "［配图暂不可用，稍后将重试下载］"})
        if reference.url:
            blocks.append({"type": "heading", "text": "参考来源"})
            blocks.append({"type": "paragraph", "text": reference.url})
            for source in re.findall(r"来源：(https://www\.luogu\.com\.cn/article/[A-Za-z0-9_-]+)", reference.content):
                if source != reference.url:
                    blocks.append({"type": "paragraph", "text": source})
        title = f"{'CF' if problem.source == 'cf' else 'AT'} {problem.key} · {problem.original_name}"
        html = build_html(
            title=title, subtitle="题解", blocks=blocks,
            meta_items=[("难度", problem.difficulty), ("rating", str(problem.rating))],
            footer_text="AlgoQuest · 题解与参考配图",
        )
        digest = hashlib.sha256((str(SOLUTION_RENDER_VERSION) + html).encode()).hexdigest()[:24]
        directory = SOLUTION_DIR / re.sub(r"[^A-Za-z0-9_.-]", "_", key)
        path = directory / f"{digest}.png"
        if not path.is_file():
            temporary = path.with_suffix(".tmp.png")
            try:
                await render_html_to_png(html, temporary)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return path
