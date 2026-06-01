"""Convert problem markdown blocks to a styled HTML page and render it to PNG via Playwright."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from nonebot.log import logger

_render_lock = asyncio.Lock()

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Noto Sans CJK SC", "Microsoft YaHei", "DejaVu Sans", sans-serif;
    font-size: 17px; line-height: 1.8;
    color: #111827; background: #f1f5f9;
    padding: 36px 44px;
  }
  .card {
    max-width: 1000px; margin: 0 auto;
    background: #ffffff; border-radius: 18px;
    padding: 40px 48px 32px 48px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    position: relative; overflow: hidden;
  }
  .card::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0;
    height: 4px; background: linear-gradient(90deg, #2563eb 0%, #d97706 100%);
  }
  h1 { font-size: 26px; font-weight: 700; color: #0f172a; margin-bottom: 14px; }
  .subtitle { font-size: 14px; color: #64748b; margin-bottom: 24px; }
  .meta-row {
    display: flex; flex-wrap: wrap; gap: 10px;
    margin: 0 0 24px;
  }
  .meta-pill {
    display: inline-flex; align-items: center;
    min-height: 34px; padding: 6px 14px;
    border: 1px solid #cbd5e1; border-radius: 999px;
    background: #f8fafc; color: #0f172a;
    font-size: 14px; line-height: 1.4;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.85);
  }
  .meta-pill:nth-child(1) { background: #ecfeff; border-color: #a5f3fc; }
  .meta-pill:nth-child(2) { background: #f0fdf4; border-color: #bbf7d0; }
  .meta-pill:nth-child(3) { background: #fff7ed; border-color: #fed7aa; }
  .meta-label { color: #475569; font-weight: 700; }
  .meta-value { color: #0f172a; font-weight: 700; }
  strong { font-weight: 800; color: #0f172a; }
  h2 { font-size: 19px; font-weight: 700; color: #0f766e;
       margin: 20px 0 6px; padding-bottom: 4px;
       border-bottom: 1px solid #e2e8f0; }
  p { margin: 8px 0; }
  ul, ol { margin: 8px 0 8px 24px; }
  li { margin: 4px 0; }
  .note {
    margin: 18px 0; padding: 14px 18px;
    border-left: 4px solid #d97706;
    background: #fffbeb; border-radius: 10px;
  }
  .note-title {
    color: #92400e; font-weight: 700; margin-bottom: 6px;
  }
  .note p:first-child { margin-top: 0; }
  .note p:last-child { margin-bottom: 0; }
  pre, code { font-family: "DejaVu Sans Mono", monospace; }
  pre {
    background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px;
    padding: 12px 16px; margin: 10px 0; overflow-x: auto;
    font-size: 14px; line-height: 1.55; white-space: pre-wrap; word-break: break-word;
  }
  code { font-size: 0.92em; }
  img { display: block; max-width: 100%; height: auto; margin: 14px auto; border-radius: 8px; }
  table { border-collapse: collapse; margin: 12px 0; width: 100%; }
  td, th { border: 1px solid #cbd5e1; padding: 6px 12px; text-align: center; }
  .footer {
    margin-top: 28px; padding-top: 14px;
    border-top: 1px solid #e2e8f0;
    font-size: 12px; color: #94a3b8; text-align: right;
  }
</style>
<script>
  MathJax = {
    tex: {
      inlineMath: [["$","$"],["\\(","\\)"]],
      displayMath: [["$$","$$"],["\\[","\\]"]],
      processEscapes: true,
    },
    startup: {
      ready() {
        MathJax.startup.defaultReady();
        MathJax.startup.promise.then(() => { window.MATHJAX_READY = true; });
      }
    },
    options: { enableMenu: false },
  };
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
</head>
<body>
<div class="card">
<h1>{title}</h1>
{meta_bar}
{body}
<div class="footer">{footer_text}</div>
</div>
</body>
</html>"""


def build_html(
    *,
    title: str,
    blocks: list[dict[str, Any]],
    subtitle: str = "",
    tag_label: str = "",
    meta_items: list[tuple[str, str]] | None = None,
    sample_pairs: list[dict[str, str]] | None = None,
    image_paths: list[str] | None = None,
    footer_text: str = "",
) -> str:
    """Build a MathJax-ready HTML page from structured blocks.

    ``"list_item"`` blocks are grouped into ``<ul>`` lists.
    """

    body_parts: list[str] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        btype = block.get("type", "paragraph")
        text = block.get("text", "")

        if btype == "list_item":
            items: list[str] = []
            while i < len(blocks) and blocks[i].get("type") == "list_item":
                items.append(f"<li>{_escape_math(blocks[i].get('text', ''))}</li>")
                i += 1
            body_parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        if btype == "ordered_list_item":
            items: list[str] = []
            while i < len(blocks) and blocks[i].get("type") == "ordered_list_item":
                items.append(f"<li>{_escape_math(blocks[i].get('text', ''))}</li>")
                i += 1
            body_parts.append("<ol>" + "".join(items) + "</ol>")
            continue

        i += 1

        if btype == "heading":
            body_parts.append(f"<h2>{_escape_math(text)}</h2>")
        elif btype == "pre":
            body_parts.append(f"<pre><code>{_escape(text)}</code></pre>")
        elif btype == "image":
            data_uri = block.get("data_uri", "")
            path = block.get("path", "")
            if data_uri:
                body_parts.append(f'<img src="{_escape_attr(data_uri)}" alt="problem image">')
            elif path:
                try:
                    import base64
                    data = Path(path).read_bytes()
                    mime = "image/png" if path.endswith(".png") else "image/jpeg"
                    b64 = base64.b64encode(data).decode()
                    body_parts.append(f'<img src="data:{mime};base64,{b64}" alt="problem image">')
                except Exception:
                    pass
        elif btype == "note":
            note_blocks = block.get("blocks") or []
            note_body = _blocks_to_body(note_blocks)
            if note_body:
                body_parts.append('<div class="note"><div class="note-title">说明</div>' + note_body + "</div>")
        else:
            body_parts.append(f"<p>{_escape_math(text)}</p>")

    # Backward compat: samples passed separately.
    if sample_pairs:
        body_parts.append("<h2>样例</h2>")
        for idx, pair in enumerate(sample_pairs, start=1):
            inp = pair.get("input", "")
            out = pair.get("output", "")
            body_parts.append(f"<h2>样例 {idx} — 输入</h2>")
            body_parts.append(f"<pre><code>{_escape(inp)}</code></pre>")
            body_parts.append(f"<h2>样例 {idx} — 输出</h2>")
            body_parts.append(f"<pre><code>{_escape(out)}</code></pre>")

    # Footer is in the HTML template, not in body_parts.

    html = _HTML_TEMPLATE
    html = html.replace("{title}", _escape(title))
    html = html.replace("{meta_bar}", _build_meta_bar(subtitle, tag_label, meta_items))
    html = html.replace("{body}", "\n".join(body_parts))
    html = html.replace("{footer_text}", _escape(footer_text))
    return html


async def render_html_to_png(html: str, output_path: Path, *, width: int = 960) -> None:
    """Render *html* to a full-page PNG using Playwright + Chromium."""

    from playwright.async_api import async_playwright

    async with _render_lock:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
            )
            page = await browser.new_page(viewport={"width": width, "height": 800})
            await page.set_content(html, wait_until="domcontentloaded", timeout=60000)

            try:
                await page.wait_for_function(
                    "window.MATHJAX_READY === true", timeout=45000,
                )
            except Exception:
                logger.warning("MathJax did not signal ready in time; capturing anyway")

            try:
                await page.evaluate(
                    """async () => {
                      if (document.fonts && document.fonts.ready) {
                        await document.fonts.ready;
                      }
                      if (window.MathJax && MathJax.typesetPromise) {
                        await MathJax.typesetPromise();
                      }
                    }"""
                )
            except Exception:
                logger.warning("Final MathJax/font settle step failed; capturing anyway")

            await page.wait_for_timeout(1800)
            await page.screenshot(path=str(output_path), full_page=True, type="png")
            await browser.close()

    logger.info(f"Rendered HTML → {output_path} ({output_path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_ESCAPE_TABLE = str.maketrans({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
})


def _escape(text: str) -> str:
    return text.translate(_ESCAPE_TABLE)


def _escape_attr(text: str) -> str:
    return _escape(text).replace("'", "&#39;")


def _escape_math(text: str) -> str:
    """HTML-escape text but preserve $ / $$ math and <img ...> tags."""
    return _escape_markdown_inline(text)


def _build_meta_bar(
    subtitle: str,
    tag_label: str,
    meta_items: list[tuple[str, str]] | None,
) -> str:
    items = [(label, value) for label, value in (meta_items or []) if value]
    if items:
        pills = [
            '<span class="meta-pill">'
            f'<span class="meta-label">{_escape(label)}：</span>'
            f'<span class="meta-value">{_escape(value)}</span>'
            "</span>"
            for label, value in items
        ]
        return '<div class="meta-row">' + "".join(pills) + "</div>"

    parts: list[str] = []
    if subtitle:
        parts.append(_escape(subtitle))
    if tag_label:
        parts.append(f'<span class="meta-pill"><span class="meta-value">{_escape(tag_label)}</span></span>')
    return f'<div class="subtitle">{" ".join(parts)}</div>' if parts else ""


def _escape_markdown_inline(text: str) -> str:
    rendered: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("<img ", i):
            end = text.find(">", i + 5)
            if end != -1:
                rendered.append(text[i : end + 1])
                i = end + 1
                continue

        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            if end != -1:
                rendered.append(text[i : end + 3])
                i = end + 3
                continue

        if text[i] == "`":
            end = text.find("`", i + 1)
            if end != -1:
                rendered.append(f"<code>{_escape(text[i + 1 : end])}</code>")
                i = end + 1
                continue

        if text.startswith("$$", i):
            end = text.find("$$", i + 2)
            if end != -1:
                rendered.append(text[i : end + 2])
                i = end + 2
                continue

        if text[i] == "$":
            end = text.find("$", i + 1)
            if end != -1 and end > i + 1:
                rendered.append(text[i : end + 1])
                i = end + 1
                continue

        if text.startswith("**", i):
            end = _find_markdown_closing(text, "**", i + 2)
            if end != -1:
                inner = text[i + 2 : end]
                if inner.strip():
                    rendered.append(_render_markdown_emphasis(inner))
                    i = end + 2
                    continue

        if text[i] == "*" and not text.startswith("**", i):
            end = _find_markdown_closing(text, "*", i + 1)
            if end != -1:
                inner = text[i + 1 : end]
                if inner.strip():
                    rendered.append(_render_markdown_emphasis(inner))
                    i = end + 1
                    continue

        rendered.append(_escape(text[i]))
        i += 1
    return "".join(rendered)


def _find_markdown_closing(text: str, delimiter: str, start: int) -> int:
    i = start
    while i < len(text):
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end == -1:
                return -1
            i = end + 1
            continue

        if text.startswith("$$", i):
            end = text.find("$$", i + 2)
            if end == -1:
                return -1
            i = end + 2
            continue

        if text[i] == "$":
            end = text.find("$", i + 1)
            if end == -1:
                return -1
            i = end + 1
            continue

        if delimiter == "*" and text.startswith("**", i):
            i += 2
            continue

        if text.startswith(delimiter, i):
            return i

        i += 1
    return -1


def _render_markdown_emphasis(inner: str) -> str:
    stripped = inner.strip()
    if _looks_like_math_emphasis(stripped):
        return _markdown_emphasis_to_math(stripped)
    return f"<strong>{_escape_markdown_inline(inner)}</strong>"


def _looks_like_math_emphasis(text: str) -> bool:
    if not text:
        return False
    if text.startswith("$") and text.endswith("$"):
        return True
    if any(ch in text for ch in ("\\", "_", "^", "{", "}", "|")):
        return True
    if re.fullmatch(r"[A-Za-z]", text):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", text):
        return any(ch.isdigit() or ch == "_" for ch in text) or text in {"dist", "gcd", "lcm", "mex", "mod"}
    return bool(re.fullmatch(r"[A-Za-z0-9_]+\s*[+\-*/=<>]\s*[A-Za-z0-9_]+", text))


def _markdown_emphasis_to_math(text: str) -> str:
    if text.startswith("$") and text.endswith("$"):
        return text
    return f"${text}$"


def _blocks_to_body(blocks: list[dict[str, Any]]) -> str:
    body_parts: list[str] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        btype = block.get("type", "paragraph")
        text = block.get("text", "")

        if btype == "list_item":
            items: list[str] = []
            while i < len(blocks) and blocks[i].get("type") == "list_item":
                items.append(f"<li>{_escape_math(blocks[i].get('text', ''))}</li>")
                i += 1
            body_parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        if btype == "ordered_list_item":
            items: list[str] = []
            while i < len(blocks) and blocks[i].get("type") == "ordered_list_item":
                items.append(f"<li>{_escape_math(blocks[i].get('text', ''))}</li>")
                i += 1
            body_parts.append("<ol>" + "".join(items) + "</ol>")
            continue

        i += 1
        if btype == "heading":
            body_parts.append(f"<h2>{_escape_math(text)}</h2>")
        elif btype == "pre":
            body_parts.append(f"<pre><code>{_escape(text)}</code></pre>")
        elif btype == "image":
            data_uri = block.get("data_uri", "")
            if data_uri:
                body_parts.append(f'<img src="{_escape_attr(data_uri)}" alt="problem image">')
        elif btype == "note":
            nested = _blocks_to_body(block.get("blocks") or [])
            if nested:
                body_parts.append('<div class="note"><div class="note-title">说明</div>' + nested + "</div>")
        else:
            body_parts.append(f"<p>{_escape_math(text)}</p>")

    return "\n".join(body_parts)
