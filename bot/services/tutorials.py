"""Cached official/community tutorial references and their illustration assets."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import re
import time
from dataclasses import asdict, dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from nonebot.log import logger
from PIL import Image

from bot.services.deepseek import _config
from bot.services.paths import runtime_data_dir

TUTORIAL_CACHE_DIR = runtime_data_dir() / "tutorials"
IMAGE_CACHE_DIR = TUTORIAL_CACHE_DIR / "images"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
_IMAGE_RE = re.compile(
    r'!\[(?P<alt>[^\]]*)\]\(\s*(?:<(?P<angle>[^>]+)>|(?P<url>[^\s]+?))(?:\s+["\'][^"\']*["\'])?\s*\)'
    r'|<img\b[^>]*>', re.IGNORECASE,
)
_locks: dict[str, asyncio.Lock] = {}
_retry_after: dict[str, float] = {}
_image_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class TutorialReference:
    content: str = ""
    url: str = ""
    title: str = ""


def _number(key: str, default: float) -> float:
    try:
        return max(1, float(_config(key, str(default))))
    except ValueError:
        return default


def luogu_problem_id(problem: Any) -> str:
    pid = ("AT_" if problem.source == "at" else "CF") + problem.key
    if not re.fullmatch(r"(?:CF\d+[A-Za-z]\d*|AT_[A-Za-z0-9_]+)", pid):
        raise ValueError("Invalid Luogu problem id")
    return pid


def _page_data(text: str) -> dict[str, Any]:
    soup = BeautifulSoup(text, "html.parser")
    node = soup.find("script", id="lentille-context")
    if node:
        context = json.loads(node.string or node.get_text())
        if isinstance(context, dict) and isinstance(context.get("data"), dict):
            return context["data"]
    match = re.search(r'decodeURIComponent\(["\'](.*?)["\']\)', text)
    if match:
        context = json.loads(unquote(match.group(1)))
        if isinstance(context, dict):
            return context.get("currentData", context)
    raise ValueError("Missing Luogu page data")


def _solution_items(data: dict[str, Any], pid: str) -> list[dict[str, Any]]:
    problem = data.get("problem")
    if isinstance(problem, dict) and problem.get("pid"):
        if str(problem["pid"]).lower() != pid.lower():
            raise ValueError("Luogu tutorial problem mismatch")
    for key in ("solutions", "solution", "articles"):
        value = data.get(key)
        if isinstance(value, dict):
            value = value.get("result", value.get("data", []))
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _article(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("article", "solution"):
        if isinstance(item.get(key), dict):
            return item[key]
    return item


def _cached_references(path: Path, pid: str) -> tuple[list[TutorialReference], float]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("references"), list):
            return [], 0
        if data.get("pid") != pid or data.get("selection") != "time-last-v1":
            return [], 0
        refs = [TutorialReference(**item) for item in data["references"] if isinstance(item, dict)]
        refs = [ref for ref in refs if isinstance(ref.content, str) and isinstance(ref.url, str)]
        refs = [ref for ref in refs if ref.content.strip() and ref.url.startswith("https://www.luogu.com.cn/")]
        return refs, float(data["fetched_at"])
    except (OSError, ValueError, TypeError, KeyError):
        return [], 0


async def _luogu_get(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> httpx.Response:
    for _ in range(5):
        if urlsplit(url).scheme != "https" or urlsplit(url).netloc != "www.luogu.com.cn":
            raise ValueError("Unexpected Luogu redirect host")
        response = await client.get(url, headers=headers)
        if response.is_redirect:
            url = urljoin(url, response.headers.get("location", ""))
            continue
        response.raise_for_status()
        return response
    raise ValueError("Too many Luogu redirects")


def _last_solution_page(data: dict[str, Any]) -> int:
    solutions = data.get("solutions", {})
    if not isinstance(solutions, dict):
        return 1
    count = max(0, int(solutions.get("count") or 0))
    per_page = max(1, int(solutions.get("perPage") or 20))
    return max(1, (count + per_page - 1) // per_page)


async def luogu_references(problem: Any) -> list[TutorialReference]:
    if _config("LUOGU_SOLUTIONS_ENABLED", "true").lower() not in {"1", "true", "yes", "enabled"}:
        return []
    pid = luogu_problem_id(problem)
    async with _locks.setdefault(pid, asyncio.Lock()):
        path = TUTORIAL_CACHE_DIR / "luogu" / f"{pid}.json"
        cached, fetched_at = _cached_references(path, pid)
        if cached and time.time() - fetched_at < _number("LUOGU_SOLUTION_CACHE_TTL_SECONDS", 604800):
            return cached
        cookie = _config("LUOGU_COOKIE").strip()
        if not cookie or time.time() < _retry_after.get(pid, 0):
            return cached
        headers = {
            "User-Agent": _config("LUOGU_USER_AGENT", "Mozilla/5.0"),
            "Referer": f"https://www.luogu.com.cn/problem/{pid}",
        }
        stage = "login_setup"
        try:
            parsed_cookie = SimpleCookie()
            parsed_cookie.load(cookie)
            jar = httpx.Cookies()
            for key, morsel in parsed_cookie.items():
                jar.set(key, morsel.value, domain="www.luogu.com.cn", path="/")
            proxy = _config("PROBLEM_HTTP_PROXY").strip()
            async with httpx.AsyncClient(
                timeout=_number("LUOGU_HTTP_TIMEOUT_SECONDS", 30),
                follow_redirects=False, cookies=jar,
                **({"proxy": proxy} if proxy else {}),
            ) as client:
                stage = "solution_list"
                listing_url = f"https://www.luogu.com.cn/problem/solution/{pid}?orderBy=time"
                response = await _luogu_get(client, listing_url, headers)
                data = _page_data(response.text)
                items = _solution_items(data, pid)
                listing = data.get("solutions")
                if isinstance(listing, dict) and listing.get("count") == 0 and not items:
                    logger.info(f"No Luogu tutorials published for {pid}; using cached/official reference")
                    _retry_after[pid] = time.time() + 300
                    return cached
                last_page = _last_solution_page(data)
                if last_page > 1:
                    stage = "last_solution_page"
                    response = await _luogu_get(client, f"{listing_url}&page={last_page}", headers)
                    items = _solution_items(_page_data(response.text), pid)
                refs = []
                for item in items[-1:]:
                    article = _article(item)
                    lid = str(article.get("lid") or article.get("id") or "")
                    if not re.fullmatch(r"[A-Za-z0-9_-]+", lid):
                        continue
                    url = f"https://www.luogu.com.cn/article/{lid}"
                    content = article.get("content")
                    if not isinstance(content, str) or not content.strip() or article.get("contentFull") is False:
                        stage = "article_content"
                        article_response = await _luogu_get(client, url, headers)
                        article = _article(_page_data(article_response.text))
                        content = article.get("content")
                    if isinstance(content, str) and content.strip():
                        refs.append(TutorialReference(
                            content=content, url=url,
                            title=str(article.get("title") or f"{pid} 社区题解"),
                        ))
                if not refs:
                    raise ValueError("No readable Luogu solutions")
            stage = "cache_write"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"pid": pid, "selection": "time-last-v1", "fetched_at": time.time(), "references": [asdict(ref) for ref in refs]}
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
            _retry_after.pop(pid, None)
            logger.info(f"Cached {len(refs)} Luogu tutorial(s) for {pid}")
            return refs
        except Exception as exc:
            reasons = {
                "Missing Luogu page data": "missing_page_data",
                "Luogu tutorial problem mismatch": "problem_mismatch",
                "Unexpected Luogu redirect host": "unexpected_redirect_host",
                "Too many Luogu redirects": "too_many_redirects",
                "No readable Luogu solutions": "no_readable_solution_content",
            }
            reason = reasons.get(str(exc), type(exc).__name__)
            if isinstance(exc, httpx.HTTPStatusError):
                reason = f"HTTP_{exc.response.status_code}"
            logger.warning(
                f"Luogu tutorial unavailable for {pid} (stage={stage}, reason={reason}); "
                "using cached/official reference"
            )
            _retry_after[pid] = time.time() + 300
            return cached


async def problem_reference(
    problem: Any, *, tutorial_text: str | None = None, tutorial_url: str | None = None,
) -> TutorialReference:
    official = tutorial_text if tutorial_text is not None else getattr(problem, "tutorial_text", "")
    official_url = tutorial_url if tutorial_url is not None else getattr(problem, "tutorial_url", "")
    refs = await luogu_references(problem)
    parts = [official.strip()] if official.strip() else []
    for ref in refs:
        parts.append(f"## 洛谷社区题解：{ref.title}\n来源：{ref.url}\n\n{ref.content}")
    return TutorialReference(
        content="\n\n".join(parts),
        url=official_url or (refs[0].url if refs else ""),
        title="参考题解",
    )


def image_links(markdown: str, base_url: str = "") -> list[tuple[str, str]]:
    links = []
    visible = re.sub(r"(?ms)^\s*\x60{3}.*?^\s*\x60{3}[^\n]*", "", markdown)
    for match in _IMAGE_RE.finditer(visible):
        if match.group(0).lower().startswith("<img"):
            node = BeautifulSoup(match.group(0), "html.parser").find("img")
            url, alt = str(node.get("src") or ""), str(node.get("alt") or "参考题解配图")
        else:
            url, alt = match.group("angle") or match.group("url") or "", match.group("alt") or "参考题解配图"
        url = urljoin(base_url, url)
        parsed = urlsplit(url)
        if parsed.scheme in {"https", "http"} and parsed.hostname:
            links.append((url, alt))
    return list(dict.fromkeys(links))


async def cache_image(client: httpx.AsyncClient, url: str) -> str | None:
    async with _image_locks.setdefault(url, asyncio.Lock()):
        return await _cache_image(client, url)


async def _cache_image(client: httpx.AsyncClient, url: str) -> str | None:
    key = hashlib.sha256(url.encode()).hexdigest()
    path = IMAGE_CACHE_DIR / f"{key}.png"
    svg_path = IMAGE_CACHE_DIR / f"{key}.svg"
    for cached, mime in ((path, "image/png"), (svg_path, "image/svg+xml")):
        if cached.is_file():
            return f"data:{mime};base64," + base64.b64encode(cached.read_bytes()).decode()
    try:
        async with client.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            chunks = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ValueError("Image exceeds size limit")
                chunks.append(chunk)
            raw = b"".join(chunks)
            mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if mime == "image/svg+xml":
            from xml.etree import ElementTree
            root = ElementTree.fromstring(raw)
            if root.tag.rsplit("}", 1)[-1] != "svg":
                raise ValueError("Invalid SVG")
            path, output, mime = svg_path, raw, "image/svg+xml"
        else:
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image dimensions exceed limit")
                image.seek(0)
                converted = image.convert("RGBA")
                buffer = io.BytesIO()
                converted.save(buffer, format="PNG")
                output, mime = buffer.getvalue(), "image/png"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(output)
        temporary.replace(path)
        return f"data:{mime};base64," + base64.b64encode(output).decode()
    except Exception as exc:
        logger.warning(f"Tutorial illustration unavailable ({type(exc).__name__})")
        return None
