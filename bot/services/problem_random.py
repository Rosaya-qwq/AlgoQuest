from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
from dotenv import load_dotenv
from nonebot.log import logger
from PIL import Image, ImageDraw, ImageFont

_env_path = Path(".env")
if _env_path.exists():
    load_dotenv(_env_path)


def _env_float(key: str, default: float) -> float:
    try:
        return max(0.1, float(os.environ.get(key, str(default))))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(key, str(default))))
    except ValueError:
        return default


def _env_nonnegative_int(key: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(key, str(default))))
    except ValueError:
        return default


def _env_rating_range(key: str, default_min: int, default_max: int | None) -> tuple[int, int | None]:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default_min, default_max
    parts = [part.strip() for part in re.split(r"[,:\s]+", raw) if part.strip()]
    if len(parts) != 2:
        return default_min, default_max
    try:
        min_rating = max(0, int(float(parts[0])))
        max_part = parts[1].lower()
        max_rating = None if max_part in {"inf", "infinity", "+inf", "none"} else max(0, int(float(parts[1])))
    except ValueError:
        return default_min, default_max
    if max_rating is not None and max_rating <= min_rating:
        return default_min, default_max
    return min_rating, max_rating


def _env_csv(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    values = tuple(part.strip().rstrip("/") for part in raw.split(",") if part.strip())
    return values or default


def _env_text(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


CF_DATA_DIR = Path("data/codeforces")
ATCODER_DATA_DIR = Path("data/atcoder")
DATA_DIR = CF_DATA_DIR
PROBLEM_CACHE_PATH = CF_DATA_DIR / "problemset.json"
ATCODER_CACHE_PATH = ATCODER_DATA_DIR / "problemset.json"
LEGACY_ATCODER_CACHE_PATH = CF_DATA_DIR / "atcoder_problemset.json"
RENDER_CACHE_VERSION_PATH = Path("data/render_cache_version.json")
STATE_DIR = CF_DATA_DIR / "states"
RENDERED_DIR = CF_DATA_DIR / "rendered"
ATCODER_STATE_DIR = ATCODER_DATA_DIR / "states"
ATCODER_RENDERED_DIR = ATCODER_DATA_DIR / "rendered"

PROBLEMSET_CACHE_TTL_SECONDS = 24 * 60 * 60
HTTP_TIMEOUT_SECONDS = _env_float("CODEFORCES_HTTP_TIMEOUT_SECONDS", 60.0)
ATCODER_HTTP_TIMEOUT_SECONDS = _env_float("ATCODER_HTTP_TIMEOUT_SECONDS", 60.0)
TUTORIAL_TIMEOUT_SECONDS = _env_float("TUTORIAL_TIMEOUT_SECONDS", 900.0)
TUTORIAL_FETCH_ATTEMPTS = _env_int("TUTORIAL_FETCH_ATTEMPTS", 5)
PROBLEM_FETCH_RETRY_DELAY_SECONDS = _env_float("PROBLEM_FETCH_RETRY_DELAY_SECONDS", 5.0)
PROBLEMSET_FETCH_RETRY_DELAY_SECONDS = _env_float("PROBLEMSET_FETCH_RETRY_DELAY_SECONDS", 10.0)
PROBLEM_FETCH_MAX_ROUNDS = _env_nonnegative_int("PROBLEM_FETCH_MAX_ROUNDS", 0)
PROBLEM_STARTUP_FETCH_MAX_ROUNDS = _env_nonnegative_int("PROBLEM_STARTUP_FETCH_MAX_ROUNDS", 1)
PROBLEM_BUFFER_MAINTENANCE_INTERVAL_SECONDS = _env_float("PROBLEM_BUFFER_MAINTENANCE_INTERVAL_SECONDS", 60.0)
ATCODER_API_REQUEST_INTERVAL_SECONDS = _env_float("ATCODER_API_REQUEST_INTERVAL_SECONDS", 1.1)
CODEFORCES_CLOUDSCRAPER_ENABLED = _env_text("CODEFORCES_CLOUDSCRAPER_ENABLED", "true").lower() in {
    "1", "true", "yes", "enabled",
}
MAX_FETCH_ATTEMPTS = 10
RENDER_VERSION = 17
ATCODER_REGULAR_CONTEST_RE = re.compile(r"^(?:abc|arc|agc|atc)\d+$", re.IGNORECASE)
DEFAULT_HTTP_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
CODEFORCES_USER_AGENT = _env_text("CODEFORCES_USER_AGENT", DEFAULT_HTTP_USER_AGENT)
ATCODER_USER_AGENT = _env_text("ATCODER_USER_AGENT", DEFAULT_HTTP_USER_AGENT)
CODEFORCES_COOKIE = _env_text("CODEFORCES_COOKIE")
ATCODER_COOKIE = _env_text("ATCODER_COOKIE")
CODEFORCES_COOKIES_FILE = _env_text("CODEFORCES_COOKIES_FILE")
ATCODER_COOKIES_FILE = _env_text("ATCODER_COOKIES_FILE")

CODEFORCES_API_PROBLEMSET = "https://codeforces.com/api/problemset.problems"
ATCODER_PROBLEMS_API = "https://kenkoooo.com/atcoder/resources/merged-problems.json"
ATCODER_MODELS_API = "https://kenkoooo.com/atcoder/resources/problem-models.json"
PROBLEM_PAGE_BASES = _env_csv("CODEFORCES_PROBLEM_PAGE_BASES", (
    "https://codeforces.com/problemset/problem",
    "https://mirror.codeforces.com/problemset/problem",
))
PROBLEM_CONTEST_PAGE_BASES = _env_csv("CODEFORCES_CONTEST_PAGE_BASES", (
    "https://codeforces.com/contest",
    "https://mirror.codeforces.com/contest",
))


@dataclass(frozen=True)
class Difficulty:
    key: str
    display_name: str
    min_rating: int
    max_rating: int | None

    def contains(self, rating: int) -> bool:
        if rating < self.min_rating:
            return False
        return self.max_rating is None or rating < self.max_rating

    @property
    def range_text(self) -> str:
        if self.max_rating is None:
            return f"[{self.min_rating}, inf)"
        return f"[{self.min_rating}, {self.max_rating})"


_DEFAULT_RATING_RANGES: dict[str, tuple[int, int | None]] = {
    "check-in": (0, 1200),
    "easy": (1200, 1800),
    "medium": (1800, 2400),
    "hard": (2400, 3000),
    "impossible": (3000, None),
}
_DIFFICULTY_DISPLAY_NAMES: dict[str, str] = {
    "check-in": "Check-in",
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
    "impossible": "Impossible",
}
_DIFFICULTY_ENV_SUFFIXES: dict[str, str] = {
    "check-in": "CHECK_IN",
    "easy": "EASY",
    "medium": "MEDIUM",
    "hard": "HARD",
    "impossible": "IMPOSSIBLE",
}


def _build_difficulties_from_env(prefix: str) -> dict[str, Difficulty]:
    difficulties: dict[str, Difficulty] = {}
    for key, (default_min, default_max) in _DEFAULT_RATING_RANGES.items():
        min_rating, max_rating = _env_rating_range(
            f"{prefix}_RATING_{_DIFFICULTY_ENV_SUFFIXES[key]}",
            default_min,
            default_max,
        )
        difficulties[key] = Difficulty(key, _DIFFICULTY_DISPLAY_NAMES[key], min_rating, max_rating)
    return difficulties


DIFFICULTIES: dict[str, Difficulty] = _build_difficulties_from_env("CF")
ATCODER_DIFFICULTIES: dict[str, Difficulty] = _build_difficulties_from_env("AT")

DIFFICULTIES_BY_SOURCE: dict[str, dict[str, Difficulty]] = {
    "cf": DIFFICULTIES,
    "at": ATCODER_DIFFICULTIES,
}

SOURCE_ALIASES: dict[str, str] = {
    "cf": "cf",
    "codeforces": "cf",
    "codeforce": "cf",
    "codeforces.com": "cf",
    "at": "at",
    "atcoder": "at",
    "atcoder.jp": "at",
}


def _is_regular_atcoder_contest(contest_id: str) -> bool:
    return bool(ATCODER_REGULAR_CONTEST_RE.fullmatch(contest_id.strip()))


def _request_headers_for_source(source: str) -> dict[str, str]:
    if source == "at":
        user_agent = ATCODER_USER_AGENT
        cookie = _cookie_header(
            direct_cookie=ATCODER_COOKIE,
            cookie_file=ATCODER_COOKIES_FILE,
            domain_hint="atcoder.jp",
        )
    else:
        user_agent = CODEFORCES_USER_AGENT
        cookie = _cookie_header(
            direct_cookie=CODEFORCES_COOKIE,
            cookie_file=CODEFORCES_COOKIES_FILE,
            domain_hint="codeforces.com",
        )

    headers = {"User-Agent": user_agent or DEFAULT_HTTP_USER_AGENT}
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _cookie_header(*, direct_cookie: str, cookie_file: str, domain_hint: str) -> str:
    if direct_cookie:
        return direct_cookie
    if not cookie_file:
        return ""
    path = Path(os.path.expandvars(cookie_file)).expanduser()
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning(f"Configured cookie file is not readable: {path}")
        return ""
    if not text:
        return ""
    if text.startswith("[") or text.startswith("{"):
        parsed = _cookie_header_from_json(text, domain_hint)
    else:
        parsed = _cookie_header_from_netscape(text, domain_hint)
    if parsed:
        return parsed
    if "\n" not in text and "\t" not in text and "=" in text:
        return text
    return ""


def _cookie_header_from_json(text: str, domain_hint: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    cookies: list[dict[str, Any]]
    if isinstance(payload, list):
        cookies = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        raw_cookies = payload.get("cookies")
        cookies = [item for item in raw_cookies if isinstance(item, dict)] if isinstance(raw_cookies, list) else []
        if not cookies and "name" in payload and "value" in payload:
            cookies = [payload]
    else:
        return ""
    pairs: list[str] = []
    for cookie in cookies:
        domain = str(cookie.get("domain") or "")
        if domain and not _cookie_domain_matches(domain, domain_hint):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _cookie_header_from_netscape(text: str, domain_hint: str) -> str:
    pairs: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#HttpOnly_"):
            line = line.removeprefix("#HttpOnly_")
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
        if not _cookie_domain_matches(domain, domain_hint):
            continue
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _cookie_domain_matches(domain: str, domain_hint: str) -> bool:
    domain = domain.strip().lstrip(".").lower()
    domain_hint = domain_hint.strip().lstrip(".").lower()
    return domain == domain_hint or domain.endswith("." + domain_hint)


DIFFICULTY_ALIASES: dict[str, str] = {
    "check-in": "check-in",
    "checkin": "check-in",
    "check_in": "check-in",
    "ci": "check-in",
    "签到": "check-in",
    "入门": "check-in",
    "easy": "easy",
    "简单": "easy",
    "medium": "medium",
    "中等": "medium",
    "hard": "hard",
    "困难": "hard",
    "impossible": "impossible",
    "地狱": "impossible",
    "不可做": "impossible",
}


def normalize_source(raw: str) -> str | None:
    return SOURCE_ALIASES.get(raw.strip().lower())


@dataclass(frozen=True)
class ProblemRef:
    contest_id: int
    index: str
    name: str
    rating: int
    tags: list[str]
    source: str = "cf"
    atcoder_task_id: str = ""
    atcoder_contest_id: str = ""

    @property
    def key(self) -> str:
        if self.source == "at":
            return self.atcoder_task_id or f"{self.atcoder_contest_id}_{self.index}"
        return f"{self.contest_id}{self.index}"

    @property
    def safe_key(self) -> str:
        safe_index = re.sub(r"[^A-Za-z0-9_.-]", "_", self.index)
        if self.source == "at":
            safe_task = re.sub(r"[^A-Za-z0-9_.-]", "_", self.key)
            return f"at_{safe_task}"
        return f"cf_{self.contest_id}_{safe_index}"

    @property
    def url(self) -> str:
        if self.source == "at":
            return f"https://atcoder.jp/contests/{self.atcoder_contest_id}/tasks/{self.atcoder_task_id}"
        return f"https://codeforces.com/problemset/problem/{self.contest_id}/{self.index}"


@dataclass
class RenderedProblem:
    contest_id: int
    index: str
    rating: int
    tags: list[str]
    original_name: str
    url: str
    difficulty: str
    statement_image: str
    samples_image: str
    generated_at: str
    time_limit: str = ""
    memory_limit: str = ""
    source: str = "cf"
    obfuscation: str = "disabled"
    ai_brief: str = ""
    statement_text: str = ""
    tutorial_url: str = ""
    tutorial_text: str = ""
    render_version: int = RENDER_VERSION

    @property
    def key(self) -> str:
        if self.source == "at":
            return self.index
        return f"{self.contest_id}{self.index}"


_locks: dict[str, asyncio.Lock] = {
    f"{source}:{key}": asyncio.Lock()
    for source, difficulties in DIFFICULTIES_BY_SOURCE.items()
    for key in difficulties
}
_warm_tasks: dict[str, asyncio.Task[None]] = {}
_maintenance_task: asyncio.Task[None] | None = None


def normalize_difficulty(raw: str) -> str | None:
    normalized = raw.strip().lower()
    return DIFFICULTY_ALIASES.get(normalized)


def parse_source_difficulty_args(
    raw: str,
    *,
    default_source: str = "cf",
    require_source: bool = False,
) -> tuple[str | None, str | None, str]:
    parts = raw.strip().split(maxsplit=2)
    if not parts:
        return None, None, ""

    first_source = normalize_source(parts[0])
    if first_source is not None:
        if len(parts) < 2:
            return first_source, None, ""
        difficulty_key = normalize_difficulty(parts[1])
        rest = parts[2].strip() if len(parts) > 2 else ""
        return first_source, difficulty_key, rest

    if require_source:
        return None, None, raw.strip()

    difficulty_key = normalize_difficulty(parts[0])
    rest = parts[1].strip() if len(parts) > 1 else ""
    return default_source, difficulty_key, rest


def difficulty_usage(command: str = "/giveup") -> str:
    lines = [f"用法：{command} <cf|at> <难度>", "Codeforces 难度："]
    for difficulty in DIFFICULTIES.values():
        lines.append(f"- cf {difficulty.key}: rating {difficulty.range_text}")
    lines.append("AtCoder 难度：")
    for difficulty in ATCODER_DIFFICULTIES.values():
        lines.append(f"- at {difficulty.key}: difficulty {difficulty.range_text}")
    lines.append("中文别名：签到、简单、中等、困难、地狱")
    return "\n".join(lines)


def _state_key(source: str, difficulty_key: str) -> str:
    return f"{source}:{difficulty_key}"


def _get_difficulties(source: str) -> dict[str, Difficulty]:
    return DIFFICULTIES_BY_SOURCE[source]


def _state_dir_for(source: str) -> Path:
    return ATCODER_STATE_DIR if source == "at" else STATE_DIR


def _rendered_dir_for(source: str) -> Path:
    return ATCODER_RENDERED_DIR if source == "at" else RENDERED_DIR


def sync_render_cache_version() -> str:
    """Clear rendered caches when the declared render version changes."""
    payload = _load_json(RENDER_CACHE_VERSION_PATH)
    old_version: int | None = None
    if isinstance(payload, dict) and "render_version" in payload:
        try:
            old_version = int(payload.get("render_version"))
        except (TypeError, ValueError):
            old_version = -1

    if old_version is not None and old_version != RENDER_VERSION:
        _clear_render_cache()
        status = f"cleared {old_version}->{RENDER_VERSION}"
    elif old_version is None:
        status = "initialized"
    else:
        status = "ok"

    _save_json(
        RENDER_CACHE_VERSION_PATH,
        {"render_version": RENDER_VERSION, "updated_at": _utc_now()},
    )
    return status


def _clear_render_cache() -> None:
    """Remove state and rendered-image caches while keeping problemset caches."""
    import shutil

    for path in (STATE_DIR, RENDERED_DIR, ATCODER_STATE_DIR, ATCODER_RENDERED_DIR):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def has_ready_current(difficulty_key: str, source: str = "cf") -> bool:
    state = _load_state(difficulty_key, source)
    current = state.get("cur_state")
    return bool(current and _rendered_files_exist(current))


def get_current_problem(difficulty_key: str, source: str = "cf") -> RenderedProblem | None:
    state = _load_state(difficulty_key, source)
    return _read_rendered_problem(state.get("cur_state"))


def read_problem_markdown(problem: RenderedProblem) -> str:
    if problem.statement_text:
        return problem.statement_text
    problem_dir = Path(problem.statement_image).parent
    for filename in ("problem_post.md", "problem_pre.md"):
        path = problem_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def read_problem_tutorial(problem: RenderedProblem) -> str:
    return problem.tutorial_text or ""


def start_problem_buffer_maintenance() -> None:
    """Start a background loop that fills incomplete buffers when the bot is idle."""
    global _maintenance_task
    if _maintenance_task is not None and not _maintenance_task.done():
        return
    _maintenance_task = asyncio.create_task(_maintain_problem_buffers_forever())


async def _maintain_problem_buffers_forever() -> None:
    while True:
        try:
            await ensure_all_difficulties_on_startup(start_maintenance=False)
        except Exception:
            logger.exception("Problem buffer maintenance iteration failed")
        await asyncio.sleep(PROBLEM_BUFFER_MAINTENANCE_INTERVAL_SECONDS)


async def claim_problem(difficulty_key: str, source: str = "cf") -> RenderedProblem:
    async with _locks[_state_key(source, difficulty_key)]:
        state = _load_state(difficulty_key, source)
        current = _read_rendered_problem(state.get("cur_state"))
        upcoming = _read_rendered_problem(state.get("next_state"))

        if current is None:
            if upcoming is not None:
                current = upcoming
                upcoming = None
            else:
                current = await _build_random_problem(difficulty_key, source=source)

        state["cur_state"] = asdict(upcoming) if upcoming is not None else None
        state["next_state"] = None
        state["updated_at"] = _utc_now()
        _save_state(difficulty_key, state, source)
        cleanup_unreferenced_rendered_dirs(source=source)

    return current


async def giveup_to_next(difficulty_key: str, source: str = "cf") -> RenderedProblem:
    """Discard the current problem and immediately return the cached next one.

    Replenish the buffer afterwards via :func:`warm_states_in_background`.
    If no *next_state* is available, builds a fresh problem synchronously
    (excluding the current problem's key when possible).
    """
    async with _locks[_state_key(source, difficulty_key)]:
        state = _load_state(difficulty_key, source)
        upcoming = _read_rendered_problem(state.get("next_state"))
        old_cur = _read_rendered_problem(state.get("cur_state"))

        if upcoming is not None:
            # Promote next_state → cur_state, clear next.
            state["cur_state"] = state["next_state"]
            state["next_state"] = None
            state["updated_at"] = _utc_now()
            _save_state(difficulty_key, state, source)

            # Clean up old problem files.
            _cleanup_rendered_dir(old_cur)
            cleanup_unreferenced_rendered_dirs(source=source)

            return upcoming

        # No buffered next — build one immediately, trying not to repeat.
        used_keys: set[str] = set()
        if old_cur is not None:
            used_keys.add(old_cur.key)

        # Discard current to force a fresh pick.
        state["cur_state"] = None
        state["next_state"] = None
        state["updated_at"] = _utc_now()
        _save_state(difficulty_key, state, source)

        _cleanup_rendered_dir(old_cur)

    new_problem = await _build_random_problem(difficulty_key, used_keys, source=source)

    async with _locks[_state_key(source, difficulty_key)]:
        state = _load_state(difficulty_key, source)
        state["cur_state"] = asdict(new_problem)
        state["next_state"] = None
        state["updated_at"] = _utc_now()
        _save_state(difficulty_key, state, source)
        cleanup_unreferenced_rendered_dirs(source=source)

    return new_problem


def warm_states_in_background(difficulty_key: str, exclude_keys: set[str] | None = None, source: str = "cf") -> None:
    task_key = _state_key(source, difficulty_key)
    task = _warm_tasks.get(task_key)
    if task is not None and not task.done():
        return
    _warm_tasks[task_key] = asyncio.create_task(
        _ensure_buffered_states(difficulty_key, exclude_keys or set(), source=source)
    )


async def refresh_all_difficulties_on_startup() -> dict[str, str]:
    """Refresh cur_state and next_state for every source/difficulty at bot startup."""
    results: dict[str, str] = {}
    logger.info("Refreshing problem buffers for all sources/difficulties...")
    for source, difficulties in DIFFICULTIES_BY_SOURCE.items():
        for difficulty_key, difficulty in difficulties.items():
            result_key = _state_key(source, difficulty_key)
            started_at = time.monotonic()
            try:
                await refresh_difficulty_buffer(difficulty_key, source=source)
                elapsed = time.monotonic() - started_at
                results[result_key] = "ok"
                logger.info(
                    f"Refreshed {source} {difficulty.display_name} buffer in {elapsed:.1f}s"
                )
            except Exception as exc:
                elapsed = time.monotonic() - started_at
                results[result_key] = f"failed: {exc}"
                logger.exception(
                    f"Failed to refresh {source} {difficulty.display_name} buffer after {elapsed:.1f}s"
                )
    cleanup_unreferenced_rendered_dirs()
    logger.info(f"Codeforces startup refresh finished: {results}")
    return results


async def ensure_all_difficulties_on_startup(*, start_maintenance: bool = True) -> dict[str, str]:
    """Ensure cur_state and next_state exist without replacing valid cached problems."""
    version_status = sync_render_cache_version()
    results: dict[str, str] = {"render_cache": version_status}
    logger.info(f"Checking problem buffers for all sources/difficulties; render cache {version_status}")
    for source, difficulties in DIFFICULTIES_BY_SOURCE.items():
        for difficulty_key, difficulty in difficulties.items():
            result_key = _state_key(source, difficulty_key)
            started_at = time.monotonic()
            try:
                current, upcoming, changed = await ensure_difficulty_buffer(
                    difficulty_key,
                    source=source,
                    max_rounds=PROBLEM_STARTUP_FETCH_MAX_ROUNDS,
                )
                elapsed = time.monotonic() - started_at
                if changed:
                    results[result_key] = "filled"
                    logger.info(
                        f"Filled missing {source} {difficulty.display_name} buffer in {elapsed:.1f}s"
                    )
                else:
                    results[result_key] = "cached"
                    logger.info(
                        f"Kept cached {source} {difficulty.display_name} buffer "
                        f"({current.key}, {upcoming.key})"
                    )
            except Exception as exc:
                elapsed = time.monotonic() - started_at
                results[result_key] = f"failed: {exc}"
                logger.exception(
                    f"Failed to ensure {source} {difficulty.display_name} buffer after {elapsed:.1f}s"
                )
    cleanup_unreferenced_rendered_dirs()
    logger.info(f"Problem startup ensure finished: {results}")
    if start_maintenance:
        start_problem_buffer_maintenance()
    return results


async def ensure_difficulty_buffer(
    difficulty_key: str,
    source: str = "cf",
    *,
    max_rounds: int | None = None,
) -> tuple[RenderedProblem, RenderedProblem, bool]:
    """Fill missing current/next slots and keep existing valid rendered problems."""
    async with _locks[_state_key(source, difficulty_key)]:
        state = _load_state(difficulty_key, source)
        current = _read_rendered_problem(state.get("cur_state"))
        upcoming = _read_rendered_problem(state.get("next_state"))
        changed = False

        used_keys: set[str] = set()
        if not _is_complete_rendered_problem(current):
            _cleanup_rendered_dir(current)
            current = await _build_random_problem(difficulty_key, source=source, max_rounds=max_rounds)
            changed = True
        used_keys.add(current.key)

        if not _is_complete_rendered_problem(upcoming):
            _cleanup_rendered_dir(upcoming)
            upcoming = await _build_random_problem(difficulty_key, used_keys, source=source, max_rounds=max_rounds)
            changed = True

        if changed:
            state["cur_state"] = asdict(current)
            state["next_state"] = asdict(upcoming)
            state["updated_at"] = _utc_now()
            state["startup_ensured_at"] = _utc_now()
            _save_state(difficulty_key, state, source)
            cleanup_unreferenced_rendered_dirs(source=source)
        return current, upcoming, changed


async def refresh_difficulty_buffer(
    difficulty_key: str,
    source: str = "cf",
) -> tuple[RenderedProblem, RenderedProblem]:
    async with _locks[_state_key(source, difficulty_key)]:
        first = await _build_random_problem(difficulty_key, source=source)
        second = await _build_random_problem(difficulty_key, {first.key}, source=source)

        state = _load_state(difficulty_key, source)
        old_current = _read_rendered_problem(state.get("cur_state"))
        old_next = _read_rendered_problem(state.get("next_state"))
        state["cur_state"] = asdict(first)
        state["next_state"] = asdict(second)
        state["updated_at"] = _utc_now()
        state["startup_refreshed_at"] = _utc_now()
        _save_state(difficulty_key, state, source)

        new_keys = {first.key, second.key}
        if old_current is None or old_current.key not in new_keys:
            _cleanup_rendered_dir(old_current)
        if old_next is None or old_next.key not in new_keys:
            _cleanup_rendered_dir(old_next)
        cleanup_unreferenced_rendered_dirs(source=source)
        return first, second


async def _ensure_buffered_states(
    difficulty_key: str,
    exclude_keys: set[str],
    source: str = "cf",
) -> None:
    async with _locks[_state_key(source, difficulty_key)]:
        state = _load_state(difficulty_key, source)
        current = _read_rendered_problem(state.get("cur_state"))
        upcoming = _read_rendered_problem(state.get("next_state"))

        used_keys = set(exclude_keys)
        if not _is_complete_rendered_problem(current):
            _cleanup_rendered_dir(current)
            current = await _build_random_problem(difficulty_key, used_keys, source=source)
            used_keys.add(current.key)
        else:
            used_keys.add(current.key)

        if not _is_complete_rendered_problem(upcoming):
            _cleanup_rendered_dir(upcoming)
            upcoming = await _build_random_problem(difficulty_key, used_keys, source=source)

        state["cur_state"] = asdict(current)
        state["next_state"] = asdict(upcoming)
        state["updated_at"] = _utc_now()
        _save_state(difficulty_key, state, source)
        cleanup_unreferenced_rendered_dirs(source=source)


async def _build_random_problem(
    difficulty_key: str,
    exclude_keys: set[str] | None = None,
    source: str = "cf",
    *,
    max_rounds: int | None = None,
) -> RenderedProblem:
    exclude_keys = exclude_keys or set()
    difficulty = _get_difficulties(source)[difficulty_key]
    problems = await _load_problem_pool(difficulty, source=source)
    candidates = [problem for problem in problems if problem.key not in exclude_keys]
    if not candidates:
        candidates = problems

    last_error: Exception | None = None
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT_SECONDS,
        headers=_request_headers_for_source(source),
        follow_redirects=True,
    ) as client:
        round_index = 0
        while True:
            round_index += 1
            random.shuffle(candidates)
            for problem in candidates[:MAX_FETCH_ATTEMPTS]:
                try:
                    return await _render_problem(client, difficulty_key, problem, source=source)
                except Exception as exc:  # noqa: BLE001 - random fallback should continue.
                    last_error = exc
                    logger.warning(
                        f"Failed to fetch/render {source} {difficulty_key} problem "
                        f"{problem.key} on round {round_index}: {exc}"
                    )
            effective_max_rounds = PROBLEM_FETCH_MAX_ROUNDS if max_rounds is None else max_rounds
            if effective_max_rounds and round_index >= effective_max_rounds:
                break
            logger.warning(
                f"No {source} {difficulty_key} problem rendered in round {round_index}; "
                f"retrying after {PROBLEM_FETCH_RETRY_DELAY_SECONDS:.1f}s"
            )
            await asyncio.sleep(PROBLEM_FETCH_RETRY_DELAY_SECONDS)

    if last_error is not None:
        source_name = "Codeforces" if source == "cf" else "AtCoder"
        raise RuntimeError(f"无法抓取并渲染 {source_name} 题面：{last_error}") from last_error
    return_source = "Codeforces" if source == "cf" else "AtCoder"
    raise RuntimeError(f"{return_source} {difficulty.display_name} 难度池为空")


async def _load_problem_pool(difficulty: Difficulty, source: str = "cf") -> list[ProblemRef]:
    if source == "at":
        return await _load_atcoder_problem_pool(difficulty)

    payload = _load_problemset_cache()
    if payload is None or _is_cache_expired(payload):
        try:
            payload = await _fetch_problemset_with_retry("cf")
            _save_json(PROBLEM_CACHE_PATH, payload)
        except Exception:
            cached_payload = _load_problemset_cache()
            if cached_payload is None:
                raise
            payload = cached_payload

    problems: list[ProblemRef] = []
    for raw_problem in payload.get("problems", []):
        contest_id = raw_problem.get("contestId")
        index = raw_problem.get("index")
        rating = raw_problem.get("rating")
        problem_type = raw_problem.get("type")
        tags = raw_problem.get("tags") or []

        if not isinstance(contest_id, int):
            continue
        if not isinstance(index, str) or not index:
            continue
        if not isinstance(rating, int) or not difficulty.contains(rating):
            continue
        if problem_type and problem_type != "PROGRAMMING":
            continue
        if "*special" in tags:
            continue

        problems.append(
            ProblemRef(
                source="cf",
                contest_id=contest_id,
                index=index,
                name=str(raw_problem.get("name") or ""),
                rating=rating,
                tags=list(tags),
            )
        )

    if not problems:
        raise RuntimeError(f"没有找到 rating {difficulty.range_text} 的 Codeforces 题目")
    return problems


async def _fetch_problemset() -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT_SECONDS,
        headers=_request_headers_for_source("cf"),
    ) as client:
        response = await client.get(CODEFORCES_API_PROBLEMSET)
        response.raise_for_status()
        payload = response.json()

    if payload.get("status") != "OK":
        raise RuntimeError(f"Codeforces API 返回异常：{payload.get('comment', payload)}")

    result = payload.get("result") or {}
    problems = result.get("problems")
    if not isinstance(problems, list):
        raise RuntimeError("Codeforces API 响应中缺少 problems 列表")

    return {"fetched_at": time.time(), "problems": problems}


async def _fetch_problemset_with_retry(source: str) -> dict[str, Any]:
    attempt = 0
    while True:
        attempt += 1
        try:
            if source == "at":
                return await _fetch_atcoder_problemset()
            return await _fetch_problemset()
        except Exception as exc:
            logger.warning(
                f"Failed to fetch {source} problemset on attempt {attempt}: {exc}; "
                f"retrying after {PROBLEMSET_FETCH_RETRY_DELAY_SECONDS:.1f}s",
                exc_info=True,
            )
            await asyncio.sleep(PROBLEMSET_FETCH_RETRY_DELAY_SECONDS)


async def _load_atcoder_problem_pool(difficulty: Difficulty) -> list[ProblemRef]:
    payload = _load_atcoder_cache()
    if payload is None or _is_cache_expired(payload):
        try:
            payload = await _fetch_problemset_with_retry("at")
            _save_json(ATCODER_CACHE_PATH, payload)
        except Exception:
            cached_payload = _load_atcoder_cache()
            if cached_payload is None:
                raise
            payload = cached_payload

    problems_by_id = payload.get("problems") or {}
    models = payload.get("models") or {}
    refs: list[ProblemRef] = []
    if not isinstance(problems_by_id, dict) or not isinstance(models, dict):
        return refs

    for problem_id, problem in problems_by_id.items():
        if not isinstance(problem, dict):
            continue
        model = models.get(problem_id) or {}
        if not isinstance(model, dict):
            continue
        raw_rating = model.get("difficulty")
        try:
            rating = int(round(float(raw_rating)))
        except (TypeError, ValueError):
            continue
        if rating < 0 or not difficulty.contains(rating):
            continue

        contest_id = str(problem.get("contest_id") or "").strip()
        title = str(problem.get("title") or problem_id).strip()
        if not contest_id or not str(problem_id).strip():
            continue
        if not _is_regular_atcoder_contest(contest_id):
            continue
        refs.append(
            ProblemRef(
                source="at",
                contest_id=0,
                index=str(problem_id),
                name=title,
                rating=rating,
                tags=[],
                atcoder_task_id=str(problem_id),
                atcoder_contest_id=contest_id,
            )
        )

    if not refs:
        raise RuntimeError(f"没有找到 difficulty {difficulty.range_text} 的 AtCoder 题目")
    return refs


async def _fetch_atcoder_problemset() -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=ATCODER_HTTP_TIMEOUT_SECONDS,
        headers=_request_headers_for_source("at"),
        follow_redirects=True,
    ) as client:
        problems_response = await client.get(ATCODER_PROBLEMS_API)
        problems_response.raise_for_status()
        await asyncio.sleep(ATCODER_API_REQUEST_INTERVAL_SECONDS)
        models_response = await client.get(ATCODER_MODELS_API)
        models_response.raise_for_status()

    problems_raw = problems_response.json()
    models = models_response.json()
    if not isinstance(problems_raw, list):
        raise RuntimeError("AtCoder problems API 响应不是列表")
    if not isinstance(models, dict):
        raise RuntimeError("AtCoder problem-models API 响应不是对象")
    problems = {
        str(problem.get("id")): problem
        for problem in problems_raw
        if isinstance(problem, dict) and problem.get("id")
    }
    return {"fetched_at": time.time(), "problems": problems, "models": models}


async def _render_problem(
    client: httpx.AsyncClient,
    difficulty_key: str,
    problem: ProblemRef,
    source: str = "cf",
) -> RenderedProblem:
    problem_dir = _rendered_dir_for(source) / problem.safe_key
    metadata_path = problem_dir / "metadata.json"
    image_path = problem_dir / "combined.png"

    cached = _read_rendered_problem(_load_json(metadata_path))
    if cached is not None and cached.source == source:
        return cached

    raw_html = await _fetch_problem_html(client, problem)
    problem_dir.mkdir(parents=True, exist_ok=True)
    tutorial_url = _extract_tutorial_url(raw_html, problem.url) if source == "cf" else ""
    tutorial_text = await _fetch_tutorial_text(client, tutorial_url, problem) if tutorial_url else ""

    if source == "at":
        statement_blocks, sample_pairs, images, limits = _parse_atcoder_problem_html(raw_html, problem.url)
    else:
        statement_blocks, sample_pairs, images, limits = _parse_problem_html(raw_html, problem.url)
    statement_blocks = await _materialize_image_blocks(client, statement_blocks, images)
    statement_blocks = _sanitize_block_math(statement_blocks)

    # DeepSeek only processes text blocks.
    obfuscation_mode: str = "disabled"
    deepseek_model: str = ""
    try:
        from bot.services.deepseek import DeepSeekClient

        deepseek = DeepSeekClient(difficulty_key=difficulty_key)
        if deepseek.enabled:
            deepseek_model = deepseek._model
            obfuscated = await deepseek.obfuscate_statement(statement_blocks)
            if obfuscated:
                statement_blocks = _restore_image_data(obfuscated, statement_blocks)
                statement_blocks = _sanitize_block_math(statement_blocks)
                obfuscation_mode = "deepseek"
    except Exception:
        logger.exception("DeepSeek translation failed, using original text")

    statement_blocks, note_blocks = _move_notes_after_samples(statement_blocks)

    # Merge statement + samples + notes.
    all_blocks = list(statement_blocks)
    if sample_pairs:
        all_blocks.append({"type": "heading", "text": "样例"})
        for idx, pair in enumerate(sample_pairs, start=1):
            all_blocks.append({"type": "heading", "text": f"样例 {idx} — 输入"})
            all_blocks.append({"type": "pre", "text": pair.get("input", "")})
            all_blocks.append({"type": "heading", "text": f"样例 {idx} — 输出"})
            all_blocks.append({"type": "pre", "text": pair.get("output", "")})
    all_blocks.extend(note_blocks)
    statement_text = _blocks_to_plain_text(all_blocks)
    ai_brief = await _generate_cached_solution_brief(
        problem=problem,
        difficulty_key=difficulty_key,
        statement_text=statement_text,
        tutorial_text=tutorial_text,
        tutorial_url=tutorial_url,
    )

    # Build HTML and render.
    difficulty = DIFFICULTIES_BY_SOURCE[source][difficulty_key]
    footer = deepseek_model if obfuscation_mode == "deepseek" else ""

    from bot.services.html_render import build_html, render_html_to_png

    html_content = build_html(
        title="Codeforces Practice" if source == "cf" else "AtCoder Practice",
        meta_items=[
            ("难度", difficulty.key),
            ("时间", limits.get("time_limit") or "未知"),
            ("空间", limits.get("memory_limit") or "未知"),
        ],
        blocks=all_blocks,
        sample_pairs=[],
        image_paths=[],
        footer_text=footer,
    )

    await render_html_to_png(html_content, image_path)

    rendered = RenderedProblem(
        source=source,
        contest_id=problem.contest_id,
        index=problem.key if source == "at" else problem.index,
        rating=problem.rating,
        tags=problem.tags,
        original_name=problem.name,
        url=problem.url,
        difficulty=difficulty_key,
        statement_image=str(image_path),
        samples_image=str(image_path),
        generated_at=_utc_now(),
        time_limit=limits.get("time_limit", ""),
        memory_limit=limits.get("memory_limit", ""),
        obfuscation=obfuscation_mode,
        ai_brief=ai_brief,
        statement_text=statement_text,
        tutorial_url=tutorial_url,
        tutorial_text=tutorial_text,
        render_version=RENDER_VERSION,
    )
    _save_json(metadata_path, asdict(rendered))
    return rendered


async def _generate_cached_solution_brief(
    *,
    problem: ProblemRef,
    difficulty_key: str,
    statement_text: str,
    tutorial_text: str,
    tutorial_url: str,
) -> str:
    try:
        from bot.services.deepseek import generate_solution_brief

        return await generate_solution_brief(
            _problem_ref_info(problem),
            statement_text,
            tutorial_text=tutorial_text,
            tutorial_url=tutorial_url,
            difficulty_key=difficulty_key,
        )
    except Exception:
        logger.exception("Failed to generate cached solution brief")
        return ""


def _problem_ref_info(problem: ProblemRef) -> dict[str, Any]:
    return {
        "source": problem.source,
        "contest_id": problem.contest_id,
        "index": problem.index,
        "name": problem.name,
        "rating": problem.rating,
        "tags": problem.tags,
        "url": problem.url,
    }


async def _fetch_problem_html(client: httpx.AsyncClient, problem: ProblemRef) -> str:
    if problem.source == "at":
        response = await client.get(problem.url, timeout=ATCODER_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        if 'id="task-statement"' not in response.text and "task-statement" not in response.text:
            raise RuntimeError(f"页面中没有 task-statement：{problem.url}")
        return response.text

    last_error: Exception | None = None
    attempted_urls: list[str] = []
    for base in PROBLEM_PAGE_BASES:
        url = f"{base}/{problem.contest_id}/{problem.index}?locale=en"
        attempted_urls.append(url)
        try:
            response = await client.get(url)
            response.raise_for_status()
            if "problem-statement" not in response.text:
                raise RuntimeError(f"页面中没有 problem-statement：{url}")
            return response.text
        except Exception as exc:  # noqa: BLE001 - try mirror fallback.
            last_error = exc
    for base in PROBLEM_CONTEST_PAGE_BASES:
        url = f"{base}/{problem.contest_id}/problem/{problem.index}?locale=en"
        attempted_urls.append(url)
        try:
            response = await client.get(url)
            response.raise_for_status()
            if "problem-statement" not in response.text:
                raise RuntimeError(f"页面中没有 problem-statement：{url}")
            return response.text
        except Exception as exc:  # noqa: BLE001 - try contest URL fallback.
            last_error = exc
    if CODEFORCES_CLOUDSCRAPER_ENABLED:
        for url in attempted_urls:
            try:
                html = await _fetch_with_cloudscraper(url, timeout=HTTP_TIMEOUT_SECONDS)
                if "problem-statement" not in html:
                    raise RuntimeError(f"cloudscraper 页面中没有 problem-statement：{url}")
                return html
            except Exception as exc:  # noqa: BLE001 - best-effort Cloudflare fallback.
                last_error = exc
                logger.warning(f"cloudscraper failed for {url}: {exc}")
    raise RuntimeError(
        "无法获取题面 HTML；可能是 Codeforces Cloudflare challenge、镜像站 503，"
        f"或服务器网络无法访问。已尝试：{', '.join(attempted_urls)}；最后错误：{last_error}"
    ) from last_error


async def _fetch_problem_html_with_cloudscraper(url: str) -> str:
    return await _fetch_with_cloudscraper(url, timeout=HTTP_TIMEOUT_SECONDS)


async def _fetch_with_cloudscraper(url: str, *, timeout: float) -> str:
    return await asyncio.to_thread(_fetch_with_cloudscraper_sync, url, timeout)


def _fetch_problem_html_with_cloudscraper_sync(url: str) -> str:
    return _fetch_with_cloudscraper_sync(url, HTTP_TIMEOUT_SECONDS)


def _fetch_with_cloudscraper_sync(url: str, timeout: float) -> str:
    try:
        import cloudscraper
    except ImportError as exc:
        raise RuntimeError("未安装 cloudscraper，请重新安装依赖：python -m pip install -e .") from exc

    headers = _request_headers_for_source("cf")
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "linux",
            "desktop": True,
        }
    )
    response = scraper.get(
        url,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def _extract_tutorial_url(raw_html: str, problem_url: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    candidates: list[str] = []
    fallback_blog_links: list[str] = []

    for link in soup.find_all("a", href=True):
        href = str(link.get("href") or "").strip()
        if not href:
            continue
        text = _clean_text(link.get_text(" ", strip=True)).lower()
        href_lower = href.lower()
        is_blog_entry = "/blog/entry/" in href_lower
        if is_blog_entry and "tutorial" in text:
            candidates.insert(0, href)
        elif is_blog_entry and any(keyword in text for keyword in ("tutorial", "editorial", "analysis", "题解")):
            candidates.append(href)
        elif is_blog_entry:
            fallback_blog_links.append(href)

    chosen = candidates[0] if candidates else (fallback_blog_links[0] if fallback_blog_links else "")
    if not chosen:
        return ""
    if chosen.startswith("//"):
        return "https:" + chosen
    return urljoin(problem_url, chosen)


async def _fetch_tutorial_text(
    client: httpx.AsyncClient,
    tutorial_url: str,
    problem: ProblemRef,
) -> str:
    last_error: Exception | None = None
    html = ""
    for attempt in range(1, TUTORIAL_FETCH_ATTEMPTS + 1):
        try:
            response = await client.get(tutorial_url, timeout=TUTORIAL_TIMEOUT_SECONDS)
            response.raise_for_status()
            html = response.text
            break
        except Exception as exc:  # noqa: BLE001 - best-effort official tutorial fetch.
            last_error = exc
            logger.warning(
                f"Failed to fetch Codeforces tutorial on attempt {attempt}/"
                f"{TUTORIAL_FETCH_ATTEMPTS}: {tutorial_url}",
                exc_info=True,
            )
            if attempt < TUTORIAL_FETCH_ATTEMPTS:
                await asyncio.sleep(1.5 * attempt)
    else:
        if CODEFORCES_CLOUDSCRAPER_ENABLED:
            try:
                html = await _fetch_with_cloudscraper(tutorial_url, timeout=TUTORIAL_TIMEOUT_SECONDS)
            except Exception as exc:  # noqa: BLE001 - tutorial is best effort.
                last_error = exc
                logger.warning(f"cloudscraper failed for Codeforces tutorial: {tutorial_url} ({exc})")
        if not html:
            logger.warning(f"Giving up Codeforces tutorial fetch: {tutorial_url} ({last_error})")
            return ""

    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select(".ttypography")
    if not nodes:
        nodes = soup.select(".blog-entry-content, .content")

    texts = [
        _normalize_tutorial_text(node.get_text("\n", strip=True))
        for node in nodes
    ]
    texts = [text for text in texts if len(text) >= 80]
    if not texts:
        texts = [_normalize_tutorial_text(soup.get_text("\n", strip=True))]

    if not texts:
        return ""

    selected = _select_tutorial_text(texts, problem)
    return _slice_tutorial_for_problem(selected, problem)


def _select_tutorial_text(texts: list[str], problem: ProblemRef) -> str:
    markers = _tutorial_markers(problem)
    for text in texts:
        lowered = text.lower()
        if any(marker and marker.lower() in lowered for marker in markers):
            return text
    return max(texts, key=len)


def _slice_tutorial_for_problem(text: str, problem: ProblemRef) -> str:
    markers = _tutorial_markers(problem)
    lowered = text.lower()
    marker_pos = -1
    for marker in markers:
        if not marker:
            continue
        marker_pos = lowered.find(marker.lower())
        if marker_pos >= 0:
            break

    if marker_pos < 0:
        return text[:20000]

    start = max(0, marker_pos - 2000)
    end = min(len(text), marker_pos + 16000)
    return text[start:end]


def _tutorial_markers(problem: ProblemRef) -> list[str]:
    return [
        f"{problem.contest_id}{problem.index}",
        f"{problem.contest_id} {problem.index}",
        f"{problem.index}. {problem.name}",
        problem.name,
        f"Problem {problem.index}",
        f"{problem.index}.",
    ]


def _normalize_tutorial_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _convert_math_elements(root: Tag) -> None:
    r"""Convert Codeforces math HTML elements to LaTeX $...$ / $$...$$ tokens in-place.

    Handles:
      - <span class="math">\( ... \)</span>  → $...$
      - <span class="math"> ... </span>       → $...$ (bare content)
      - <div  class="math">\[ ... \]</div>    → $$...$$
      - Elements with class="math-tex"        → $...$ (inline) / $$...$$ (block)
    """
    for span in root.find_all("span", class_="math"):
        tex = span.get_text("", strip=True).strip()
        if tex.startswith("\\(") and tex.endswith("\\)"):
            tex = tex[2:-2].strip()
        elif tex.startswith("$") and tex.endswith("$"):
            tex = tex[1:-1].strip()
        span.replace_with(f"${tex}$")

    for div in root.find_all("div", class_="math"):
        tex = div.get_text("", strip=True).strip()
        if tex.startswith("\\[") and tex.endswith("\\]"):
            tex = tex[2:-2].strip()
        elif tex.startswith("$$") and tex.endswith("$$"):
            tex = tex[2:-2].strip()
        div.replace_with(f"$${tex}$$")

    for el in root.find_all(class_="math-tex"):
        tex = el.get_text("", strip=True).strip()
        if el.name in ("div", "p"):
            if tex.startswith("\\[") and tex.endswith("\\]"):
                tex = tex[2:-2].strip()
            el.replace_with(f"$${tex}$$")
        else:
            if tex.startswith("\\(") and tex.endswith("\\)"):
                tex = tex[2:-2].strip()
            el.replace_with(f"${tex}$")


def _extract_images(root: Tag, page_url: str) -> list[dict[str, str]]:
    """Extract <img> tags from *root*, returning local paths after download.

    Replaces each <img> with a text placeholder so the surrounding text flow
    is preserved for DeepSeek.  The caller must download the actual images
    and replace the placeholders with real ``"image"`` blocks.
    """
    from urllib.parse import urljoin

    images: list[dict[str, str]] = []
    for idx, img_tag in enumerate(root.find_all("img")):
        src = (img_tag.get("src") or "").strip()
        if not src:
            img_tag.decompose()
            continue
        abs_url = urljoin(page_url, src)
        placeholder = f"[[ABOT_IMAGE_{idx}]]"
        images.append({"url": abs_url, "placeholder": placeholder, "index": str(idx)})
        img_tag.replace_with(placeholder)
    return images


async def _materialize_image_blocks(
    client: httpx.AsyncClient,
    blocks: list[dict[str, Any]],
    images: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Replace image placeholders embedded in text blocks with image blocks."""
    if not images:
        return blocks

    data_by_placeholder: dict[str, str] = {}
    for image_info in images:
        placeholder = image_info["placeholder"]
        try:
            image_response = await client.get(image_info["url"])
            image_response.raise_for_status()
            data_by_placeholder[placeholder] = _image_response_to_data_uri(
                image_response.content,
                image_response.headers.get("content-type", ""),
                image_info["url"],
            )
        except Exception:
            logger.warning(f"Failed to download problem image: {image_info['url']}")
            data_by_placeholder[placeholder] = ""

    return _split_image_placeholders(blocks, data_by_placeholder)


def _split_image_placeholders(
    blocks: list[dict[str, Any]],
    data_by_placeholder: dict[str, str],
) -> list[dict[str, Any]]:
    pattern = re.compile(
        "(" + "|".join(re.escape(placeholder) for placeholder in data_by_placeholder) + ")"
    )
    result: list[dict[str, Any]] = []

    for block in blocks:
        block_type = block.get("type", "paragraph")
        text = str(block.get("text", ""))
        if block_type == "note":
            new_block = dict(block)
            new_block["blocks"] = _split_image_placeholders(
                list(block.get("blocks") or []),
                data_by_placeholder,
            )
            result.append(new_block)
            continue
        if block_type in {"pre", "image"} or not text or not pattern.search(text):
            result.append(block)
            continue

        for part in pattern.split(text):
            if not part:
                continue
            if part in data_by_placeholder:
                data_uri = data_by_placeholder[part]
                if data_uri:
                    result.append({"type": "image", "data_uri": data_uri})
                continue
            new_block = dict(block)
            new_block["text"] = _clean_text(part)
            if new_block["text"]:
                result.append(new_block)

    return result


def _restore_image_data(
    blocks: list[dict[str, Any]],
    original_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    image_payloads = _collect_image_payloads(original_blocks)
    image_index = 0
    restored, _ = _restore_image_data_recursive(blocks, image_payloads, image_index)
    return restored


def _collect_image_payloads(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []
    for block in blocks:
        if block.get("type") == "image":
            payloads.append({"data_uri": block.get("data_uri", ""), "path": block.get("path", "")})
        elif block.get("type") == "note":
            payloads.extend(_collect_image_payloads(list(block.get("blocks") or [])))
    return payloads


def _restore_image_data_recursive(
    blocks: list[dict[str, Any]],
    image_payloads: list[dict[str, str]],
    image_index: int,
) -> tuple[list[dict[str, Any]], int]:
    restored: list[dict[str, Any]] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "image":
            new_block = dict(block)
            if image_index < len(image_payloads):
                new_block.update(image_payloads[image_index])
                image_index += 1
            restored.append(new_block)
        elif block_type == "note":
            new_block = dict(block)
            nested, image_index = _restore_image_data_recursive(
                list(block.get("blocks") or []),
                image_payloads,
                image_index,
            )
            new_block["blocks"] = nested
            restored.append(new_block)
        else:
            restored.append(block)
    return restored, image_index


def _image_response_to_data_uri(content: bytes, content_type: str, url: str) -> str:
    import base64

    content_type = content_type.split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        suffix = url.rsplit(".", 1)[-1].lower() if "." in url else ""
        content_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "svg": "image/svg+xml",
            "webp": "image/webp",
        }.get(suffix, "image/png")

    return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"


def _move_notes_after_samples(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    statement_blocks: list[dict[str, Any]] = []
    merged_note_blocks: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") == "note":
            merged_note_blocks.extend(list(block.get("blocks") or []))
        else:
            statement_blocks.append(block)
    note_blocks = [{"type": "note", "blocks": merged_note_blocks}] if merged_note_blocks else []
    return statement_blocks, note_blocks


def _sanitize_block_math(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for block in blocks:
        new_block = dict(block)
        if new_block.get("type") == "note":
            new_block["blocks"] = _sanitize_block_math(list(new_block.get("blocks") or []))
        elif "text" in new_block and new_block.get("type") != "pre":
            new_block["text"] = _sanitize_math_delimiters(str(new_block.get("text", "")))
        sanitized.append(new_block)
    return sanitized


def _sanitize_math_delimiters(text: str) -> str:
    text = re.sub(r"\\[cC]oloneqq(?![A-Za-z])", ":=", text)
    text = _scope_latex_color_commands(text)
    text = re.sub(r"\*([A-Za-z][A-Za-z0-9_]{0,8})\$", r"$\1$", text)
    text = re.sub(r"\$([A-Za-z][A-Za-z0-9_]{0,8})\*", r"$\1$", text)
    text = re.sub(r"\${3,}(.+?)\${3,}", r"$\1$", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\$)\${3,}(?!\$)", "$", text)
    text = re.sub(r"(?<!\$)\${2}([^$]+?)\${1}(?!\$)", r"$$\1$$", text)
    text = re.sub(r"(?<!\$)\${1}([^$]+?)\${2}(?!\$)", r"$$\1$$", text)
    return text


def _scope_latex_color_commands(text: str) -> str:
    r"""Convert \color{name}{...} to scoped \textcolor{name}{...}.

    MathJax treats ``\color`` as a switch in some contexts, so formulas such as
    ``\color{red}{2}, 3`` can leak the color to following tokens.  Codeforces
    statements usually intend the two-argument scoped form.
    """
    result: list[str] = []
    i = 0
    command = "\\color"
    while i < len(text):
        if text.startswith(command, i) and _is_latex_command_boundary(text, i + len(command)):
            color_start = i + len(command)
            color_end = _balanced_brace_end(text, color_start)
            if color_end != -1:
                content_start = color_end + 1
                content_end = _balanced_brace_end(text, content_start)
                if content_end != -1:
                    color = text[color_start + 1 : color_end]
                    content = text[content_start + 1 : content_end]
                    result.append(r"\textcolor{" + color + "}{" + content + "}")
                    i = content_end + 1
                    continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _is_latex_command_boundary(text: str, pos: int) -> bool:
    return pos >= len(text) or not text[pos].isalpha()


def _balanced_brace_end(text: str, start: int) -> int:
    if start >= len(text) or text[start] != "{":
        return -1
    depth = 0
    escaped = False
    for pos in range(start, len(text)):
        ch = text[pos]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return pos
    return -1


def _blocks_to_plain_text(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in blocks:
        block_type = block.get("type", "paragraph")
        text = str(block.get("text", ""))
        if block_type == "heading":
            lines.append(f"## {text}")
        elif block_type == "pre":
            lines.append("```")
            lines.append(text)
            lines.append("```")
        elif block_type == "list_item":
            lines.append(f"- {text}")
        elif block_type == "ordered_list_item":
            lines.append(f"1. {text}")
        elif block_type == "note":
            lines.append("说明：")
            lines.append(_blocks_to_plain_text(list(block.get("blocks") or [])))
        elif block_type == "image":
            lines.append("[image]")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def _parse_problem_html(
    html: str, page_url: str = ""
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    statement = soup.select_one(".problem-statement")
    if statement is None:
        raise RuntimeError("题面 HTML 中没有 .problem-statement")

    limits = _extract_limits(statement)
    images = _extract_images(statement, page_url)
    _convert_math_elements(statement)

    for header in statement.select(".header"):
        header.decompose()

    sample_node = statement.select_one(".sample-test")
    sample_pairs = _extract_samples(sample_node)
    if sample_node is not None:
        sample_node.decompose()

    blocks: list[dict[str, Any]] = []
    for child in statement.children:
        if isinstance(child, NavigableString):
            text = _clean_text(str(child))
            if text:
                blocks.append({"type": "paragraph", "text": text})
            continue
        if not isinstance(child, Tag):
            continue
        blocks.extend(_extract_blocks(child))

    if not blocks:
        raise RuntimeError("题面解析后为空")
    return blocks, sample_pairs, images, limits


def _parse_atcoder_problem_html(
    html: str,
    page_url: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    statement = soup.select_one("#task-statement")
    if statement is None:
        statement = soup.select_one(".lang-en .part") or soup.select_one(".lang-ja .part")
    if statement is None:
        raise RuntimeError("AtCoder 题面 HTML 中没有 #task-statement")

    english = statement.select_one(".lang-en")
    if english is not None:
        statement = english

    limits = _extract_atcoder_limits(soup)
    images = _extract_images(statement, page_url)
    _convert_math_elements(statement)

    sample_pairs = _extract_atcoder_samples(statement)
    for sample_node in statement.find_all(["section", "div"]):
        title = sample_node.find(["h3", "h4"])
        title_text = _clean_text(title.get_text(" ", strip=True)).lower() if title else ""
        if title_text.startswith("sample input") or title_text.startswith("sample output"):
            sample_node.decompose()
    for title in statement.find_all(["h3", "h4", "h5"]):
        title_text = _clean_text(title.get_text(" ", strip=True)).lower()
        if title_text.startswith("sample input") or title_text.startswith("sample output"):
            pre = _find_sample_pre_after_title(title, re.compile(r"sample\s+(input|output)\s+(\d+)"))
            if pre is not None:
                pre.decompose()
            title.decompose()

    for title in statement.find_all(["h2", "h3"]):
        if _clean_text(title.get_text(" ", strip=True)).lower() in {"statement", "problem statement"}:
            title.decompose()

    blocks: list[dict[str, Any]] = []
    for child in statement.children:
        if isinstance(child, NavigableString):
            text = _clean_text(str(child))
            if text:
                blocks.append({"type": "paragraph", "text": text})
            continue
        if isinstance(child, Tag):
            blocks.extend(_extract_blocks(child))

    blocks = _drop_atcoder_title_blocks(blocks)
    if not blocks:
        raise RuntimeError("AtCoder 题面解析后为空")
    return blocks, sample_pairs, images, limits


def _extract_atcoder_limits(soup: BeautifulSoup) -> dict[str, str]:
    text = _clean_text(soup.get_text(" ", strip=True))
    time_match = re.search(
        r"Time Limit:\s*([^/\n]+?)(?=\s*/\s*Memory Limit:|\s+Memory Limit:)",
        text,
        flags=re.IGNORECASE,
    )
    memory_match = re.search(
        r"Memory Limit:\s*([0-9.]+\s*(?:KiB|MiB|GiB|KB|MB|GB|B))",
        text,
        flags=re.IGNORECASE,
    )
    return {
        "time_limit": _clean_text(time_match.group(1)) if time_match else "",
        "memory_limit": _clean_text(memory_match.group(1)) if memory_match else "",
    }


def _extract_atcoder_samples(statement: Tag) -> list[dict[str, str]]:
    samples: dict[int, dict[str, str]] = {}
    sample_title_re = re.compile(r"sample\s+(input|output)\s+(\d+)")
    for title in statement.find_all(["h3", "h4", "h5"]):
        title_text = _clean_text(title.get_text(" ", strip=True)).lower()
        match = sample_title_re.search(title_text)
        if not match:
            continue
        pre = _find_sample_pre_after_title(title, sample_title_re)
        if pre is None:
            continue
        kind = match.group(1)
        idx = int(match.group(2))
        samples.setdefault(idx, {})[kind] = _pre_text(pre)
    return [
        {"input": pair.get("input", ""), "output": pair.get("output", "")}
        for _, pair in sorted(samples.items())
        if pair.get("input") or pair.get("output")
    ]


def _find_sample_pre_after_title(title: Tag, sample_title_re: re.Pattern[str]) -> Tag | None:
    sibling = title.find_next_sibling()
    while sibling is not None:
        if isinstance(sibling, Tag):
            sibling_title = sibling if sibling.name in {"h2", "h3", "h4", "h5"} else sibling.find(["h2", "h3", "h4", "h5"])
            if sibling_title is not None:
                sibling_title_text = _clean_text(sibling_title.get_text(" ", strip=True)).lower()
                if sample_title_re.search(sibling_title_text):
                    return None
            if sibling.name == "pre":
                return sibling
            nested_pre = sibling.find("pre")
            if nested_pre is not None:
                return nested_pre
        sibling = sibling.find_next_sibling()

    container = title.parent if isinstance(title.parent, Tag) else None
    while container is not None and container.name not in {"body", "html"}:
        pre = container.find("pre")
        if pre is not None:
            return pre
        container = container.parent if isinstance(container.parent, Tag) else None
    return None


def _drop_atcoder_title_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") == "heading":
            text = _clean_text(str(block.get("text", ""))).lower()
            if text.startswith("sample input") or text.startswith("sample output"):
                continue
        result.append(block)
    return result


def _extract_limits(statement: Tag) -> dict[str, str]:
    header = statement.select_one(".header")
    if header is None:
        return {}

    time_node = header.select_one(".time-limit")
    memory_node = header.select_one(".memory-limit")
    return {
        "time_limit": _strip_limit_label(time_node.get_text(" ", strip=True) if time_node else ""),
        "memory_limit": _strip_limit_label(memory_node.get_text(" ", strip=True) if memory_node else ""),
    }


def _strip_limit_label(text: str) -> str:
    text = _clean_text(text)
    if not text:
        return ""
    text = re.sub(r"^(time limit|memory limit)\s*(per test)?\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(":： ")
    text = text.replace("seconds", "s").replace("second", "s")
    text = text.replace("megabytes", "MB").replace("megabyte", "MB")
    return text


def _extract_blocks(node: Tag, *, list_type: str | None = None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    if node.name == "script" or node.name == "style":
        return blocks

    if _is_note_like_section(node):
        blocks.append({"type": "note", "blocks": _extract_note_blocks(node)})
        return blocks

    if _has_class(node, "note"):
        blocks.append({"type": "note", "blocks": _extract_note_blocks(node)})
        return blocks

    if _has_class(node, "section-title"):
        title_text = _clean_text(node.get_text(" ", strip=True).rstrip(":"))
        if title_text:
            blocks.append({"type": "heading", "text": title_text})
        return blocks

    title = node.select_one(".section-title")
    if title is not None:
        title_text = _clean_text(title.get_text(" ", strip=True).rstrip(":"))
        if title_text:
            blocks.append({"type": "heading", "text": title_text})
        title.extract()

    if node.name == "p":
        text = _extract_inline_markup(node)
        if text:
            blocks.append({"type": "paragraph", "text": text})
        return blocks

    if node.name == "pre":
        pre_text = _pre_text(node)
        if pre_text:
            blocks.append({"type": "pre", "text": pre_text})
        return blocks

    if node.name == "table":
        table_text = _table_text(node)
        if table_text:
            blocks.append({"type": "pre", "text": table_text})
        return blocks

    if node.name in {"ul", "ol"}:
        child_list_type = "ordered_list_item" if node.name == "ol" else "list_item"
        for li in node.find_all("li", recursive=False):
            blocks.extend(_extract_blocks(li, list_type=child_list_type))
        return blocks

    if node.name == "li":
        item_blocks = _extract_list_item_blocks(node, list_type or "list_item")
        blocks.extend(item_blocks)
        return blocks

    # Inline text-level tags — flatten to plain text, do NOT create a block.
    _INLINE_TAGS = frozenset({
        "span", "code", "b", "i", "strong", "em", "sub", "sup",
        "tt", "small", "mark", "ins", "del",
    })

    if node.name in _INLINE_TAGS:
        text = _node_text_preserving_inline(node)
        if text:
            blocks.append({"type": "paragraph", "text": text})
        return blocks

    # Recursively process container children.
    if node.name in ("div", "center", "blockquote", "section", "article"):
        for child in node.children:
            if isinstance(child, Tag):
                blocks.extend(_extract_blocks(child))
            elif isinstance(child, NavigableString):
                text = _clean_text(str(child))
                if text:
                    blocks.append({"type": "paragraph", "text": text})
        return blocks

    text = _clean_text(node.get_text(" ", strip=True))
    if text:
        blocks.append({"type": "paragraph", "text": text})
    return blocks


def _extract_note_blocks(node: Tag) -> list[dict[str, Any]]:
    note_blocks: list[dict[str, Any]] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            text = _clean_text(str(child))
            if text:
                note_blocks.append({"type": "paragraph", "text": text})
        elif isinstance(child, Tag):
            if _has_class(child, "section-title"):
                continue
            note_blocks.extend(_extract_blocks(child))
    return note_blocks


def _is_note_like_section(node: Tag) -> bool:
    title = node.select_one(".section-title")
    if title is None:
        return False
    title_text = _clean_text(title.get_text(" ", strip=True).rstrip(":")).lower()
    return title_text in {"example", "examples", "sample explanation", "示例", "例子", "样例说明"}


def _extract_list_item_blocks(node: Tag, list_type: str) -> list[dict[str, Any]]:
    nested_blocks: list[dict[str, Any]] = []
    text_parts: list[str] = []

    for child in node.children:
        if isinstance(child, NavigableString):
            text = _clean_text(str(child))
            if text:
                text_parts.append(text)
            continue

        if not isinstance(child, Tag):
            continue

        if child.name in {"ul", "ol", "pre", "table"} or _has_class(child, "note"):
            nested_blocks.extend(_extract_blocks(child))
            continue

        text = _node_text_preserving_inline(child)
        if text:
            text_parts.append(text)

    blocks: list[dict[str, Any]] = []
    text = _clean_text(" ".join(text_parts))
    if text:
        blocks.append({"type": list_type, "text": text})
    blocks.extend(nested_blocks)
    return blocks


def _node_text_preserving_inline(node: Tag) -> str:
    return _extract_inline_markup(node)


def _extract_inline_markup(node: Tag) -> str:
    soup = BeautifulSoup(str(node), "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for code_node in soup.find_all(["code", "kbd", "tt"]):
        text = _clean_inline_code(code_node.get_text(" ", strip=True))
        code_node.replace_with(f"`{text}`" if text else "")
    for strong_node in soup.find_all(["b", "strong"]):
        text = _clean_text(strong_node.get_text(" ", strip=True))
        strong_node.replace_with(_format_html_emphasis_text(text, "**"))
    for emphasis_node in soup.find_all(["i", "em"]):
        text = _clean_text(emphasis_node.get_text(" ", strip=True))
        emphasis_node.replace_with(_format_html_emphasis_text(text, "*"))
    return _clean_text(soup.get_text(" ", strip=True))


def _format_html_emphasis_text(text: str, marker: str) -> str:
    if not text:
        return ""
    if _looks_like_math_text(text):
        return text if text.startswith("$") and text.endswith("$") else f"${text}$"
    return f"{marker}{text}{marker}"


def _looks_like_math_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("$") and stripped.endswith("$"):
        return True
    math_tokens = (
        "\\",
        "_",
        "^",
        "{",
        "}",
        "|",
        "\\le",
        "\\ge",
        "\\sum",
        "\\min",
        "\\max",
    )
    if any(token in stripped for token in math_tokens):
        return True
    if re.fullmatch(r"[A-Za-z]", stripped):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", stripped):
        return any(ch.isdigit() or ch == "_" for ch in stripped) or stripped in {"dist", "gcd", "lcm", "mex", "mod"}
    return bool(re.fullmatch(r"[A-Za-z0-9_]+\s*[+\-*/=<>]\s*[A-Za-z0-9_]+", stripped))


def _clean_inline_code(text: str) -> str:
    text = _clean_text(text)
    return text.replace("`", "\\`")


def _has_class(node: Tag, class_name: str) -> bool:
    return class_name in set(node.get("class") or [])


def _extract_samples(sample_node: Tag | None) -> list[dict[str, str]]:
    if sample_node is None:
        return []

    pairs: list[dict[str, str]] = []
    pending_input: str | None = None

    for child in sample_node.find_all("div", recursive=False):
        classes = set(child.get("class") or [])
        if "input" in classes:
            pending_input = _pre_text(child.find("pre"))
        elif "output" in classes:
            output_text = _pre_text(child.find("pre"))
            pairs.append({"input": pending_input or "", "output": output_text})
            pending_input = None

    return pairs


def _pre_text(node: Tag | None) -> str:
    if node is None:
        return ""

    line_nodes = node.select(".test-example-line")
    if line_nodes:
        return "\n".join(line.get_text("", strip=False).rstrip() for line in line_nodes).strip()

    node = BeautifulSoup(str(node), "html.parser")
    for br in node.find_all("br"):
        br.replace_with("\n")
    return node.get_text("", strip=False).strip("\n")


def _table_text(node: Tag) -> str:
    rows: list[str] = []
    for tr in node.find_all("tr"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = text.replace(" ", " ")
    # Replace fullwidth / CJK parentheses with ASCII equivalents.
    text = text.replace("（", "(")  # （
    text = text.replace("）", ")")  # ）
    text = text.replace("「", "[")  # 「
    text = text.replace("」", "]")  # 」
    text = text.replace("［", "[")  # ［
    text = text.replace("］", "]")  # ］
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def render_statement_image(
    problem: ProblemRef,
    difficulty: Difficulty,
    blocks: list[dict[str, str]],
    output_path: Path,
    *,
    obfuscation_note: str = "",
) -> None:
    subtitle = f"Difficulty: {difficulty.display_name}"
    title = "Codeforces Practice"
    renderer = ProblemImageRenderer(
        title=title,
        subtitle=subtitle,
        label="Statement",
        obfuscation_note=obfuscation_note,
    )
    renderer.render(blocks, output_path)


def render_samples_image(
    problem: ProblemRef,
    difficulty: Difficulty,
    sample_pairs: list[dict[str, str]],
    output_path: Path,
    *,
    obfuscation_note: str = "",
) -> None:
    subtitle = f"Difficulty: {difficulty.display_name}"
    blocks: list[dict[str, str]] = []
    if not sample_pairs:
        blocks.append({"type": "paragraph", "text": "No sample tests were found on the problem page."})
    for index, pair in enumerate(sample_pairs, start=1):
        blocks.append({"type": "heading", "text": f"样例 {index} — 输入"})
        blocks.append({"type": "pre", "text": pair.get("input") or ""})
        blocks.append({"type": "heading", "text": f"样例 {index} — 输出"})
        blocks.append({"type": "pre", "text": pair.get("output") or ""})

    renderer = ProblemImageRenderer(
        title="Codeforces Practice",
        subtitle=subtitle,
        label="样例",
        obfuscation_note=obfuscation_note,
    )
    renderer.render(blocks, output_path)


class ProblemImageRenderer:
    width = 1280
    margin_x = 72
    top_margin = 58
    bottom_margin = 58
    content_gap = 18
    line_gap = 8

    background = (238, 242, 247)
    card = (255, 255, 255)
    text = (17, 24, 39)
    muted = (71, 85, 105)
    teal = (15, 118, 110)
    blue = (37, 99, 235)
    amber = (217, 119, 6)
    pre_bg = (248, 250, 252)
    pre_border = (203, 213, 225)

    def __init__(
        self,
        title: str,
        subtitle: str,
        label: str,
        obfuscation_note: str = "",
    ) -> None:
        self.title = title
        self.subtitle = subtitle
        self.label = label
        self.obfuscation_note = obfuscation_note
        self.font_title = _load_font(42, bold=True)
        self.font_subtitle = _load_font(24)
        self.font_label = _load_font(22, bold=True)
        self.font_heading = _load_font(30, bold=True)
        self.font_body = _load_font(25)
        self.font_mono = _load_font(23, mono=True)
        self.font_footer = _load_font(20)

    def render(self, blocks: list[dict[str, str]], output_path: Path) -> None:
        measure_image = Image.new("RGB", (self.width, 100), self.background)
        draw = ImageDraw.Draw(measure_image)

        content_width = self.width - self.margin_x * 2
        y = self.top_margin + 8
        operations: list[dict[str, Any]] = []

        title_x = self.margin_x + 24  # right of the accent bar (x=72→82)
        operations.append({"kind": "accent", "y": self.top_margin})
        title_lines = self._wrap(draw, self.title, self.font_title, content_width - 260 - 24)
        for line in title_lines:
            operations.append({"kind": "text", "text": line, "font": self.font_title, "xy": (title_x, y), "fill": self.text})
            y += self._line_height(self.font_title) + 4

        operations.append({"kind": "pill", "text": self.label, "y": self.top_margin + 36})
        y += 8

        subtitle_lines = self._wrap(draw, self.subtitle, self.font_subtitle, content_width - 24)
        for line in subtitle_lines:
            operations.append({"kind": "text", "text": line, "font": self.font_subtitle, "xy": (title_x, y), "fill": self.muted})
            y += self._line_height(self.font_subtitle) + 3

        # Remember where the header ends for dynamic stripe placement.
        header_end_y = int(y)
        y += 28

        for block in blocks:
            block_type = block.get("type")
            block_text = block.get("text", "")
            if block_type == "heading":
                y += 12
                lines = self._wrap(draw, block_text, self.font_heading, content_width)
                for line in lines:
                    operations.append({"kind": "text", "text": line, "font": self.font_heading, "xy": (self.margin_x, y), "fill": self.teal})
                    y += self._line_height(self.font_heading) + 5
                y += 4
            elif block_type == "pre":
                y = self._layout_pre(draw, operations, block_text, self.margin_x, y, content_width)
            elif block_type == "image":
                y = self._layout_image(draw, operations, block["path"], self.margin_x, y, content_width)
            else:
                y = self._layout_paragraph_with_math(draw, operations, block_text, self.margin_x, y, content_width)

        footer = self.obfuscation_note or " "
        y += 8
        operations.append({"kind": "rule", "y": y})
        y += 24
        operations.append({"kind": "text", "text": footer, "font": self.font_footer, "xy": (self.margin_x, y), "fill": self.muted})
        y += self._line_height(self.font_footer)

        height = int(y + self.bottom_margin + 38)
        image = Image.new("RGB", (self.width, height), self.background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (34, 28, self.width - 34, height - 28),
            radius=28,
            fill=self.card,
        )
        stripe_y = max(self.top_margin + 78, header_end_y)  # below accent bar or title
        draw.rectangle((34, stripe_y, self.width - 34, stripe_y + 4), fill=self.blue)
        draw.rectangle((34, stripe_y + 4, self.width - 34, stripe_y + 8), fill=self.amber)

        for operation in operations:
            kind = operation["kind"]
            if kind == "text":
                draw.text(operation["xy"], operation["text"], font=operation["font"], fill=operation["fill"])
            elif kind == "accent":
                draw.rounded_rectangle(
                    (self.margin_x, operation["y"], self.margin_x + 10, operation["y"] + 78),
                    radius=5,
                    fill=self.teal,
                )
            elif kind == "pill":
                self._draw_pill(draw, operation["text"], operation["y"])
            elif kind == "pre_box":
                box = operation["box"]
                draw.rounded_rectangle(box, radius=14, fill=self.pre_bg, outline=self.pre_border, width=2)
            elif kind == "rule":
                draw.line((self.margin_x, operation["y"], self.width - self.margin_x, operation["y"]), fill=(226, 232, 240), width=2)
            elif kind == "inline_math_img":
                img = operation["image"]
                x_img, y_img = operation["xy"]
                image.paste(img, (int(x_img), int(y_img)), img)
            elif kind == "display_math_img":
                img = operation["image"]
                x_img, y_img = operation["xy"]
                image.paste(img, (int(x_img), int(y_img)), img)
            elif kind == "image_block":
                img = operation["image"]
                x_img, y_img = operation["xy"]
                if img.mode == "RGBA":
                    image.paste(img, (int(x_img), int(y_img)), img)
                else:
                    image.paste(img, (int(x_img), int(y_img)))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)

    def _layout_pre(
        self,
        draw: ImageDraw.ImageDraw,
        operations: list[dict[str, Any]],
        text: str,
        x: int,
        y: int,
        width: int,
    ) -> int:
        lines: list[str] = []
        for raw_line in (text or "").splitlines() or [""]:
            wrapped = self._wrap_mono(draw, raw_line, self.font_mono, width - 42)
            lines.extend(wrapped or [""])

        line_height = self._line_height(self.font_mono) + 7
        box_top = y
        box_height = max(58, len(lines) * line_height + 32)
        operations.append({"kind": "pre_box", "box": (x, box_top, x + width, box_top + box_height)})
        text_y = box_top + 16
        for line in lines:
            operations.append({"kind": "text", "text": line, "font": self.font_mono, "xy": (x + 22, text_y), "fill": self.text})
            text_y += line_height
        return box_top + box_height + 24

    def _layout_image(
        self,
        draw: ImageDraw.ImageDraw,
        operations: list[dict[str, Any]],
        image_path: str,
        x: int,
        y: int,
        max_width: int,
    ) -> int:
        """Layout a problem-embedded image, scaled to fit the content width."""
        try:
            img = Image.open(image_path).convert("RGBA")
        except Exception:
            return y

        iw, ih = img.size
        if iw > max_width:
            ratio = max_width / iw
            new_w = int(iw * ratio)
            new_h = int(ih * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            iw, ih = new_w, new_h

        cx = int(x + (max_width - iw) / 2)
        y += 8
        operations.append({"kind": "image_block", "image": img, "xy": (cx, int(y))})
        y += ih + 12
        return y

    def _draw_pill(self, draw: ImageDraw.ImageDraw, text: str, y: int) -> None:
        padding_x = 18
        text_width = draw.textlength(text, font=self.font_label)
        box_width = int(text_width + padding_x * 2)
        x2 = self.width - self.margin_x
        x1 = x2 - box_width
        draw.rounded_rectangle((x1, y, x2, y + 42), radius=21, fill=(236, 253, 245), outline=(153, 246, 228), width=2)
        draw.text((x1 + padding_x, y + 7), text, font=self.font_label, fill=self.teal)

    def _wrap(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return []

        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
                continue

            if current:
                lines.append(current)
            if draw.textlength(word, font=font) > max_width:
                broken = self._break_long_word(draw, word, font, max_width)
                lines.extend(broken[:-1])
                current = broken[-1]
            else:
                current = word

        if current:
            lines.append(current)
        return lines

    def _wrap_mono(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        if not text:
            return [""]
        if draw.textlength(text, font=font) <= max_width:
            return [text]
        return self._break_long_word(draw, text, font, max_width)

    def _break_long_word(
        self,
        draw: ImageDraw.ImageDraw,
        word: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        for char in word:
            candidate = current + char
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or [word]

    def _line_height(self, font: ImageFont.FreeTypeFont) -> int:
        bbox = font.getbbox("Hg")
        return bbox[3] - bbox[1]

    # ------------------------------------------------------------------
    # LaTeX math rendering helpers
    # ------------------------------------------------------------------

    def _get_math_parser(self) -> Any:
        """Lazy-init matplotlib mathtext parser (cached on the instance)."""
        if not hasattr(self, "_math_parser"):
            import matplotlib

            matplotlib.use("Agg")
            from matplotlib.mathtext import MathTextParser

            self._math_parser = MathTextParser("agg")
        return self._math_parser

    @staticmethod
    def _normalize_math(formula: str) -> str:
        """Translate LaTeX shorthands that matplotlib mathtext does not recognise."""
        import re

        # \le / \ge → \leq / \geq (only when not part of a longer command like \left)
        formula = re.sub(r"\\[cC]oloneqq(?![A-Za-z])", ":=", formula)
        formula = re.sub(r"\\le(?![A-Za-z])", r"\\leq", formula)
        formula = re.sub(r"\\ge(?![A-Za-z])", r"\\geq", formula)
        # \gets / \to are not used by Codeforces typically, but be safe.
        formula = re.sub(r"\\gets(?![A-Za-z])", r"\\leftarrow", formula)
        formula = re.sub(r"\\to(?![A-Za-z])", r"\\rightarrow", formula)
        # \implies / \iff
        formula = re.sub(r"\\implies(?![A-Za-z])", r"\\Rightarrow", formula)
        formula = re.sub(r"\\iff(?![A-Za-z])", r"\\Leftrightarrow", formula)
        return formula

    @staticmethod
    def _render_math_image(formula: str, font_size: int, display: bool = False) -> Image.Image | None:
        """Render a LaTeX formula to a transparent RGBA PIL image via matplotlib.

        Results are cached globally so the same formula is never rendered twice.
        Returns *None* when rendering fails (e.g. unsupported LaTeX construct).
        """
        cache_key = (formula, font_size, display)
        cached = _MATH_IMAGE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            import io

            import matplotlib
            matplotlib.use("Agg")
            matplotlib.rcParams["mathtext.fontset"] = "dejavuserif"
            import matplotlib.pyplot as plt

            formula = ProblemImageRenderer._normalize_math(formula)

            dpi = 100
            fig, ax = plt.subplots(figsize=(0.01, 0.01), dpi=dpi)
            ax.axis("off")
            text_obj = ax.text(
                0.5,
                0.5,
                f"${formula}$" if not display else f"$${formula}$$",
                fontsize=font_size,
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            buf = io.BytesIO()
            fig.savefig(
                buf,
                format="png",
                dpi=dpi,
                bbox_inches="tight",
                pad_inches=0.03,
                transparent=True,
            )
            plt.close(fig)
            buf.seek(0)
            img = Image.open(buf).convert("RGBA")
            _MATH_IMAGE_CACHE[cache_key] = img
            return img
        except Exception:
            try:
                plt.close("all")
            except Exception:
                pass
            return None

    @staticmethod
    def _is_valid_math(formula: str) -> bool:
        """Reject formulas that contain CJK or other non-LaTeX glyphs."""
        for ch in formula:
            cp = ord(ch)
            # CJK Unified Ideographs, CJK Extension A, CJK Compatibility
            if 0x4E00 <= cp <= 0x9FFF:
                return False
            if 0x3400 <= cp <= 0x4DBF:
                return False
            if 0xF900 <= cp <= 0xFAFF:
                return False
            # Hiragana / Katakana
            if 0x3040 <= cp <= 0x30FF:
                return False
            # Fullwidth forms
            if 0xFF00 <= cp <= 0xFFEF:
                return False
        return True

    @staticmethod
    def _segment_text(text: str) -> list[dict[str, str]]:
        """Split text into plain-text, inline-math, and display-math segments.

        Handles both ``$...$`` / ``$$...$$`` (standard markdown) and
        ``\\(...\\)`` / ``\\[...\\]`` (raw LaTeX) delimiters.
        Segments containing CJK characters are forced to text type.
        """
        import re

        # Normalise raw-LaTeX delimiters into dollar form first.
        text = re.sub(r"\\\[(.*?)\\\]", r"$$\1$$", text, flags=re.DOTALL)
        text = re.sub(r"\\\((.*?)\\\)", r"$\1$", text, flags=re.DOTALL)

        segments: list[dict[str, str]] = []

        # Step 1: extract display math $$...$$ using placeholders.
        display_formulas: dict[str, str] = {}
        counter = [0]

        def _replace_display(m: re.Match[str]) -> str:
            key = f"\x00DM{counter[0]}\x00"
            display_formulas[key] = m.group(1).strip()
            counter[0] += 1
            return key

        text_with_placeholders = re.sub(
            r"\$\$(.+?)\$\$",
            _replace_display,
            text,
            flags=re.DOTALL,
        )

        # Step 2: split on inline math $...$ within the remaining text.
        inline_parts = re.split(r"(\$[^$]+\$)", text_with_placeholders)

        for part in inline_parts:
            if not part:
                continue
            if part.startswith("$") and part.endswith("$") and len(part) >= 3:
                formula = part[1:-1].strip()
                if formula:
                    if ProblemImageRenderer._is_valid_math(formula):
                        segments.append({"type": "math", "content": formula})
                    else:
                        # CJK leaked into math markers — strip $ signs.
                        segments.append({"type": "text", "content": formula})
                continue

            # Plain text — may still contain display-math placeholders.
            placeholder_keys = list(display_formulas.keys())
            if placeholder_keys:
                placeholder_pattern = "(" + "|".join(re.escape(k) for k in placeholder_keys) + ")"
                subparts = re.split(placeholder_pattern, part)
                for sp in subparts:
                    if not sp:
                        continue
                    if sp in display_formulas:
                        formula = display_formulas[sp]
                        if ProblemImageRenderer._is_valid_math(formula):
                            segments.append({"type": "display_math", "content": formula})
                        else:
                            segments.append({"type": "text", "content": formula})
                    elif sp.strip():
                        segments.append({"type": "text", "content": sp})
            elif part.strip():
                segments.append({"type": "text", "content": part})

        return segments

    def _layout_paragraph_with_math(
        self,
        draw: ImageDraw.ImageDraw,
        operations: list[dict[str, Any]],
        text: str,
        x: int,
        y: int,
        max_width: int,
    ) -> int:
        """Layout a paragraph that may contain inline / display LaTeX math.

        Inline math is placed on the same line as surrounding text (word-wrap
        treats each math segment as an unbreakable token).  Display math is
        centred on its own line like a block-level element.
        """
        segments = self._segment_text(text)
        if not segments:
            y += self._line_height(self.font_body) + self.line_gap
            return y + self.content_gap

        # Separate display-math segments — they are block-level.
        # For each continuous run of text+inline-math segments, perform
        # line-wrapping treating math tokens as atomic.
        body_font = self.font_body
        body_line_height = self._line_height(body_font)
        math_font_size = 22  # slightly smaller than body for inline fit

        space_width = draw.textlength(" ", body_font)

        def _is_cjk(ch: str) -> bool:
            cp = ord(ch)
            return (
                0x4E00 <= cp <= 0x9FFF
                or 0x3400 <= cp <= 0x4DBF
                or 0x3000 <= cp <= 0x303F
                or 0xFF00 <= cp <= 0xFFEF
                or 0xF900 <= cp <= 0xFAFF
            )

        def _split_text_into_tokens(text_content: str) -> list[dict[str, Any]]:
            """Tokenise text: CJK characters individually; non-CJK in space-split words."""
            tokens: list[dict[str, Any]] = []
            i = 0
            n = len(text_content)
            while i < n:
                if _is_cjk(text_content[i]):
                    ch = text_content[i]
                    tokens.append({
                        "kind": "text", "content": ch,
                        "width": draw.textlength(ch, body_font),
                        "image": None,
                        "spacer": 0.0,  # no space after CJK
                    })
                    i += 1
                elif text_content[i] in (" ", "\t", "\r", "\n"):
                    i += 1
                else:
                    start = i
                    while i < n and not _is_cjk(text_content[i]) and text_content[i] not in (" ", "\t", "\r", "\n"):
                        i += 1
                    word = text_content[start:i]
                    tokens.append({
                        "kind": "text", "content": word,
                        "width": draw.textlength(word, body_font),
                        "image": None,
                        "spacer": space_width if word.isascii() and len(word) > 1 else 0.0,
                    })
            return tokens

        def _add_token_to_line(token: dict[str, Any]) -> bool:
            """Try to add *token* to *current_line*.  If it fits (or the line is
            empty and breaking is needed), append it.  Returns True when the
            token was appended (possibly after flushing the previous line)."""
            nonlocal current_width
            needed = token["width"] + token.get("spacer", 0)

            if current_line and current_width + needed > max_width:
                # Flush and start a new line.
                nonlocal y
                y += _flush_line(current_line, float(y))
                current_line.clear()
                current_width = 0.0

            # Now either the line is empty or there is room.
            if not current_line and needed > max_width:
                # Token is wider than a whole line — break it.
                if token["kind"] == "text":
                    _break_and_flush_text(token["content"], max_width)
                    return False  # already flushed through _break_and_flush_text
                # Math image too wide — place it anyway.
                pass

            current_line.append(token)
            current_width += needed
            return True

        def _break_and_flush_text(text_content: str, limit: float) -> None:
            """Break a too-wide text segment character by character and flush lines."""
            nonlocal y
            line_buf: list[dict[str, Any]] = []
            line_w = 0.0
            for ch in text_content:
                ch_w = draw.textlength(ch, body_font)
                spacer = 0.0 if _is_cjk(ch) else (space_width if ch.isascii() else 0.0)
                if line_buf and line_w + ch_w + spacer > limit:
                    y += _flush_line(line_buf, float(y))
                    line_buf.clear()
                    line_w = 0.0
                line_buf.append({
                    "kind": "text", "content": ch,
                    "width": ch_w, "image": None, "spacer": spacer,
                })
                line_w += ch_w + spacer
            if line_buf:
                y += _flush_line(line_buf, float(y))

        def _flush_line(line_tokens: list[dict[str, Any]], line_y: float) -> float:
            cx = float(x)
            max_h = float(body_line_height)
            for token in line_tokens:
                if token["kind"] == "math":
                    img = token["image"]
                    if img is not None:
                        img_y = int(line_y + body_line_height * 0.65 - img.height * 0.35)
                        operations.append({
                            "kind": "inline_math_img",
                            "image": img,
                            "xy": (int(cx), img_y),
                        })
                        max_h = max(max_h, float(img.height))
                        cx += img.width + 4
                else:
                    operations.append({
                        "kind": "text",
                        "text": token["content"],
                        "font": body_font,
                        "xy": (int(cx), int(line_y)),
                        "fill": self.text,
                    })
                    cx += token["width"] + token.get("spacer", 0)
            return max_h

        current_line: list[dict[str, Any]] = []
        current_width = 0.0

        for seg in segments:
            if seg["type"] == "display_math":
                if current_line:
                    y += _flush_line(current_line, float(y))
                    current_line.clear()
                    current_width = 0.0
                y += 6
                img = self._render_math_image(seg["content"], 24, display=True)
                if img is not None:
                    cx_mid = int(x + (max_width - img.width) / 2)
                    operations.append({"kind": "display_math_img", "image": img, "xy": (cx_mid, int(y))})
                    y += img.height + 10
                else:
                    fallback = f"$$ {seg['content']} $$"
                    operations.append({
                        "kind": "text", "text": fallback, "font": self.font_mono,
                        "xy": (int(x), int(y)), "fill": self.text,
                    })
                    y += self._line_height(self.font_mono) + 8
                y += 6
                continue

            if seg["type"] == "math":
                img = self._render_math_image(seg["content"], math_font_size)
                w = float(img.width) if img is not None else draw.textlength(seg["content"], self.font_mono)
                _add_token_to_line({"kind": "math", "content": seg["content"], "width": w, "image": img, "spacer": 4})
            elif seg["type"] == "text":
                for token in _split_text_into_tokens(seg["content"]):
                    _add_token_to_line(token)

        if current_line:
            y += _flush_line(current_line, float(y))

        y += self.content_gap
        return int(y)


# Global cache for rendered math images (keyed by formula + font_size + display).
_MATH_IMAGE_CACHE: dict[tuple[str, int, bool], Image.Image] = {}


def _load_font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    names: list[str] = []
    if mono:
        names.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
            ]
        )
    elif bold:
        names.extend(
            [
                "/mnt/c/Windows/Fonts/msyhbd.ttc",                     # 微软雅黑 Bold (WSL)
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            ]
        )
    else:
        names.extend(
            [
                "/mnt/c/Windows/Fonts/msyh.ttc",                       # 微软雅黑 Regular (WSL)
                "/mnt/c/Windows/Fonts/msyhl.ttc",                      # 微软雅黑 Light (WSL)
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            ]
        )

    for name in names:
        path = Path(name)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size, encoding="utf-8")
            except OSError:
                continue
    return ImageFont.load_default()


def _save_markdown(blocks: list[dict[str, Any]], path: Path) -> None:
    md_lines: list[str] = []
    for b in blocks:
        t = b.get("type", "paragraph")
        txt = b.get("text", "")
        if t == "heading":
            md_lines.append(f"## {txt}")
        elif t == "pre":
            md_lines.append(f"```\n{txt}\n```")
        elif t == "list_item":
            md_lines.append(f"- {txt}")
        elif t == "ordered_list_item":
            md_lines.append(f"1. {txt}")
        elif t == "image":
            md_lines.append(f"[image]")
        else:
            md_lines.append(txt)
        md_lines.append("")
    path.write_text("\n".join(md_lines), encoding="utf-8")


def _cleanup_rendered_dir(problem: RenderedProblem | None) -> None:
    """Remove the rendered problem directory from disk."""
    if problem is None:
        return
    try:
        img_path = Path(problem.statement_image)
        parent = img_path.parent
        rendered_root = _rendered_dir_for(problem.source)
        if parent.exists() and parent.is_relative_to(rendered_root):
            import shutil
            shutil.rmtree(parent, ignore_errors=True)
            logger.debug(f"Cleaned up {parent}")
    except Exception:
        pass


def cleanup_unreferenced_rendered_dirs(source: str | None = None) -> int:
    """Delete rendered problem directories not referenced by any cur/next state."""
    referenced_dirs = _referenced_rendered_dirs()
    removed_count = 0
    sources = [source] if source else list(DIFFICULTIES_BY_SOURCE)
    for current_source in sources:
        rendered_dir = _rendered_dir_for(current_source)
        if not rendered_dir.exists():
            continue
        for child in rendered_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                if child.resolve() in referenced_dirs:
                    continue
                import shutil

                shutil.rmtree(child, ignore_errors=True)
                removed_count += 1
                logger.debug(f"Removed unreferenced rendered directory: {child}")
            except Exception:
                logger.exception(f"Failed to clean rendered directory: {child}")
    return removed_count


def _referenced_rendered_dirs() -> set[Path]:
    referenced: set[Path] = set()
    for source, difficulties in DIFFICULTIES_BY_SOURCE.items():
        for difficulty_key in difficulties:
            state = _load_state(difficulty_key, source)
            for slot in ("cur_state", "next_state"):
                raw_problem = state.get(slot)
                if not isinstance(raw_problem, dict):
                    continue
                image_path = raw_problem.get("statement_image") or raw_problem.get("samples_image")
                if not image_path:
                    continue
                try:
                    referenced.add(Path(str(image_path)).parent.resolve())
                except OSError:
                    continue
    return referenced


def _state_path(difficulty_key: str) -> Path:
    return _state_path_for("cf", difficulty_key)


def _state_path_for(source: str, difficulty_key: str) -> Path:
    return _state_dir_for(source) / f"{difficulty_key}.json"


def _load_state(difficulty_key: str, source: str = "cf") -> dict[str, Any]:
    path = _state_path_for(source, difficulty_key)
    if not path.exists():
        legacy_candidates: list[Path] = []
        if source == "cf":
            legacy_candidates.extend(
                [
                    STATE_DIR / f"cf_{difficulty_key}.json",
                    STATE_DIR / f"{difficulty_key}.json",
                ]
            )
        elif source == "at":
            legacy_candidates.append(STATE_DIR / f"at_{difficulty_key}.json")
        for legacy_path in legacy_candidates:
            if legacy_path.exists():
                path = legacy_path
                break
    data = _load_json(path)
    if isinstance(data, dict):
        data.setdefault("source", source)
        data.setdefault("difficulty", difficulty_key)
        data.setdefault("cur_state", None)
        data.setdefault("next_state", None)
        return data
    return {"source": source, "difficulty": difficulty_key, "cur_state": None, "next_state": None}


def _save_state(difficulty_key: str, state: dict[str, Any], source: str = "cf") -> None:
    state["source"] = source
    state["difficulty"] = difficulty_key
    _save_json(_state_path_for(source, difficulty_key), state)


def _load_problemset_cache() -> dict[str, Any] | None:
    data = _load_json(PROBLEM_CACHE_PATH)
    return data if isinstance(data, dict) else None


def _load_atcoder_cache() -> dict[str, Any] | None:
    data = _load_json(ATCODER_CACHE_PATH)
    if not isinstance(data, dict):
        data = _load_json(LEGACY_ATCODER_CACHE_PATH)
    return data if isinstance(data, dict) else None


def _is_cache_expired(payload: dict[str, Any]) -> bool:
    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, (int, float)):
        return True
    return time.time() - fetched_at > PROBLEMSET_CACHE_TTL_SECONDS


def _read_rendered_problem(raw: Any) -> RenderedProblem | None:
    if not isinstance(raw, dict):
        return None
    if not _rendered_files_exist(raw):
        return None
    try:
        render_version = int(raw.get("render_version") or 0)
    except (TypeError, ValueError):
        render_version = 0
    if render_version < RENDER_VERSION:
        return None
    try:
        return RenderedProblem(
            source=str(raw.get("source") or "cf"),
            contest_id=int(raw["contest_id"]),
            index=str(raw["index"]),
            rating=int(raw["rating"]),
            tags=list(raw.get("tags") or []),
            original_name=str(raw.get("original_name") or ""),
            url=str(raw["url"]),
            difficulty=str(raw["difficulty"]),
            statement_image=str(raw["statement_image"]),
            samples_image=str(raw["samples_image"]),
            generated_at=str(raw["generated_at"]),
            time_limit=str(raw.get("time_limit") or ""),
            memory_limit=str(raw.get("memory_limit") or ""),
            obfuscation=str(raw.get("obfuscation") or "disabled"),
            ai_brief=str(raw.get("ai_brief") or ""),
            statement_text=str(raw.get("statement_text") or ""),
            tutorial_url=str(raw.get("tutorial_url") or ""),
            tutorial_text=str(raw.get("tutorial_text") or ""),
            render_version=render_version,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _is_complete_rendered_problem(problem: RenderedProblem | None) -> bool:
    if problem is None:
        return False
    if not problem.statement_text.strip():
        return False
    if not problem.ai_brief.strip():
        return False
    if problem.ai_brief.strip().startswith(("简要题解生成失败", "未配置 DEEPSEEK_API_KEY")):
        return False
    return Path(problem.statement_image).exists()


def _rendered_files_exist(raw: dict[str, Any]) -> bool:
    statement = raw.get("statement_image")
    return bool(statement and Path(statement).exists())


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
