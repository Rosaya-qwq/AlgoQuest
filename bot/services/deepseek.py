"""DeepSeek API integration for problem obfuscation and translation."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from nonebot.log import logger

# NoneBot2 only loads its own config vars from .env.  Explicitly load
# custom DEEPSEEK_* variables so they are visible in os.environ.
_env_path = Path(".env")
if _env_path.exists():
    load_dotenv(_env_path)

DEEPSEEK_API_KEY = "DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL = "DEEPSEEK_BASE_URL"
DEEPSEEK_MODEL = "DEEPSEEK_MODEL"
DEEPSEEK_TRANSLATION_MODEL = "DEEPSEEK_TRANSLATION_MODEL"
DEEPSEEK_SOLUTION_MODEL = "DEEPSEEK_SOLUTION_MODEL"
DEEPSEEK_OBFUSCATION = "DEEPSEEK_OBFUSCATION"
DEEPSEEK_TIMEOUT_SECONDS = "DEEPSEEK_TIMEOUT_SECONDS"
DEEPSEEK_MAX_TOKENS = "DEEPSEEK_MAX_TOKENS"

DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_TOKENS = 12000
DEFAULT_FLASH_MODEL = "deepseek-v4-flash"
DEFAULT_PRO_MODEL = "deepseek-v4-pro"
_DEEPSEEK_API_LOCKS: dict[int, asyncio.Lock] = {}


def _config(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def deepseek_timeout_seconds(default: float = DEFAULT_TIMEOUT_SECONDS) -> float:
    try:
        return max(30.0, float(_config(DEEPSEEK_TIMEOUT_SECONDS, str(default))))
    except ValueError:
        return default


def deepseek_max_tokens(default: int = DEFAULT_MAX_TOKENS) -> int:
    try:
        return max(1024, int(_config(DEEPSEEK_MAX_TOKENS, str(default))))
    except ValueError:
        return default


def deepseek_api_lock() -> asyncio.Lock:
    """Return the shared DeepSeek API lock for the current event loop."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    lock = _DEEPSEEK_API_LOCKS.get(loop_id)
    if lock is None:
        lock = asyncio.Lock()
        _DEEPSEEK_API_LOCKS[loop_id] = lock
    return lock


def deepseek_model_for(kind: str, difficulty_key: str | None = None, default: str = DEFAULT_FLASH_MODEL) -> str:
    normalized_kind = kind.upper()
    normalized_difficulty = (difficulty_key or "").upper().replace("-", "_")
    keys: list[str] = []
    if normalized_difficulty:
        keys.append(f"DEEPSEEK_{normalized_kind}_MODEL_{normalized_difficulty}")
    keys.append(f"DEEPSEEK_{normalized_kind}_MODEL")
    if kind == "judge":
        keys.append(DEEPSEEK_MODEL)
    elif kind == "translation":
        keys.append(DEEPSEEK_TRANSLATION_MODEL)
    elif kind == "solution":
        keys.append(DEEPSEEK_SOLUTION_MODEL)
        keys.append(DEEPSEEK_MODEL)
    for key in keys:
        value = _config(key).strip()
        if value:
            return value
    if kind == "translation":
        return default
    if kind in {"judge", "solution"}:
        if difficulty_key == "impossible":
            return DEFAULT_PRO_MODEL
        return DEFAULT_FLASH_MODEL
    return default


def is_obfuscation_enabled() -> bool:
    """Returns True only when the user has explicitly opted in."""
    val = _config(DEEPSEEK_OBFUSCATION, "false").strip().lower()
    return val in ("1", "true", "yes", "enabled")


def is_configured() -> bool:
    """Returns True when an API key is present (regardless of enabled flag)."""
    return bool(_config(DEEPSEEK_API_KEY))


class DeepSeekClient:
    """Thin wrapper around DeepSeek's chat-completion API (OpenAI-compatible)."""

    def __init__(self, difficulty_key: str = "") -> None:
        self._api_key = _config(DEEPSEEK_API_KEY)
        self._base_url = _config(DEEPSEEK_BASE_URL, "https://api.deepseek.com").rstrip("/")
        self._model = deepseek_model_for("translation", difficulty_key)
        self._enabled = is_obfuscation_enabled()

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._api_key)

    async def obfuscate_statement(self, blocks: list[dict[str, str]]) -> list[dict[str, str]]:
        """Obfuscate and translate problem statement blocks.

        Sends the raw text of the blocks to DeepSeek and receives
        obfuscated + translated markdown, preserving all LaTeX formulas.
        Returns the original blocks unchanged when disabled or on error.
        """
        if not self.enabled:
            return blocks

        raw_text = _blocks_to_text(blocks)
        try:
            content = await self._chat(_build_obfuscation_prompt(raw_text))
            parsed = _parse_markdown_blocks(content)
            return parsed if parsed else blocks
        except Exception:
            logger.exception("DeepSeek obfuscation failed, falling back to original")
            return blocks

    async def generate_brief(self, problem_info: dict[str, Any]) -> str:
        """Generate a 2-3 sentence Chinese summary of the problem.

        Returns empty string when disabled or on error.
        """
        if not self.enabled:
            return ""

        try:
            return await self._chat(_build_brief_prompt(problem_info))
        except Exception:
            logger.exception("DeepSeek brief generation failed")
            return ""

    async def _chat(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": deepseek_max_tokens(),
        }
        async with deepseek_api_lock():
            async with httpx.AsyncClient(timeout=deepseek_timeout_seconds()) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()


async def generate_solution_brief(
    problem_info: dict[str, Any],
    problem_statement: str,
    tutorial_text: str = "",
    tutorial_url: str = "",
    difficulty_key: str = "",
) -> str:
    """Generate a short public solution after the current problem is given up."""
    api_key = _config(DEEPSEEK_API_KEY)
    if not api_key:
        return "未配置 DEEPSEEK_API_KEY，无法生成简要题解。"

    base_url = _config(DEEPSEEK_BASE_URL, "https://api.deepseek.com").rstrip("/")
    model = deepseek_model_for("solution", difficulty_key)
    prompt = _build_solution_brief_prompt(
        problem_info,
        problem_statement,
        tutorial_text=tutorial_text,
        tutorial_url=tutorial_url,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SOLUTION_BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": min(deepseek_max_tokens(), 4096),
    }

    try:
        async with deepseek_api_lock():
            async with httpx.AsyncClient(timeout=deepseek_timeout_seconds()) as client:
                response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.exception("DeepSeek solution brief generation failed")
        return f"简要题解生成失败：{exc}"


_SYSTEM_PROMPT = (
    "You are a competitive programming problem obfuscator and translator. "
    "You receive a Codeforces problem statement and must:\n"
    "1. OBFUSCATE: Change the story context (character names, setting, scenario) "
    "while keeping the algorithmic essence, constraints, input/output format, "
    "and all numerical values IDENTICAL.\n"
    "2. TRANSLATE: Output in Simplified Chinese (zh-CN).\n"
    "3. FIX and PRESERVE LaTeX formulas: Use $...$ for inline math and $$...$$ "
    "for display math. Fix any malformed LaTeX delimiters (e.g. $$$, extra $, "
    "$$$...$$$, missing delimiters) to the standard form and remove redundant "
    "dollar signs. Do NOT change the mathematical "
    "content of formulas.\n"
    "4. Use standard markdown formatting: ## for section headings, "
    "``` for code/IO, paragraphs separated by blank lines. Use **text** "
    "or *text* only for bold emphasis; do not use italic formatting. Never "
    "use _text_ for italic or __text__ for bold; underscores often appear "
    "in variables and code. Use backticks for inline code/literals such as "
    "`1 l r`. Pay special attention to embedded formulas: do not wrap "
    "LaTeX formulas with markdown emphasis markers.\n"
    "5. Preserve structural markers exactly when they appear: [IMG], "
    ":::note, and the closing ::: marker. Keep note content inside the note "
    "marker block.\n"
    "6. Preserve unordered and ordered lists as markdown lists.\n"
    "7. Do NOT include sample test cases in the output.\n"
    "Output ONLY the obfuscated markdown, no extra commentary."
)


_SOLUTION_BRIEF_SYSTEM_PROMPT = (
    "你是算法竞赛题解助手。用户已经放弃当前题目，因此可以给出原题简要题解。"
    "必须使用简体中文回答。只输出简洁题解，不输出代码。"
    "内容包含核心观察、算法步骤和复杂度；如果题面信息不足，明确说明不确定。"
)


def _build_obfuscation_prompt(raw_text: str) -> str:
    return (
        "Obfuscate and translate the following competitive programming problem "
        "statement. Change the story context but keep the algorithmic essence and "
        "all LaTeX formulas exactly the same. Output and answer only in Simplified "
        "Chinese (zh-CN, 简体中文) using standard markdown format (no sample tests). "
        "Do not use italic formatting, do not wrap LaTeX formulas with markdown "
        "emphasis markers, and do not use _text_ for italic or __text__ for bold; "
        "use *text* or **text** for bold emphasis and backticks for inline "
        "code/literals instead:\n\n"
        + raw_text
    )


def _build_brief_prompt(problem_info: dict[str, Any]) -> str:
    tags = ", ".join(problem_info.get("tags", []) or [])
    rating = problem_info.get("rating", "")
    return (
        f"In one or two short Simplified Chinese (zh-CN, 简体中文) sentences, "
        f"briefly describe what kind of algorithm problem this is. Rating: {rating}. Tags: {tags}. "
        f"Do NOT include the problem name or any identifying details. "
        f"Just say something like '这是一道关于动态规划的算法题，需要优化状态转移。'"
    )


def _build_solution_brief_prompt(
    problem_info: dict[str, Any],
    problem_statement: str,
    *,
    tutorial_text: str = "",
    tutorial_url: str = "",
) -> str:
    tutorial_block = ""
    if tutorial_text.strip():
        tutorial_block = (
            "\n\n官方 tutorial / editorial 摘录（优先参考，如果和题面冲突以题面为准）：\n"
            f"链接：{tutorial_url or problem_info.get('tutorial_url', '')}\n"
            f"{tutorial_text[:16000]}"
        )
    return (
        "请基于下面的 Codeforces 题面给出简要题解。\n"
        "要求：使用简体中文；不要输出代码；控制在 4 到 8 句话；包含核心观察、主要算法步骤和复杂度。"
        "如果提供了官方 tutorial / editorial 摘录，请优先按其中题解主线总结。\n\n"
        f"原题：CF{problem_info.get('contest_id', '')}{problem_info.get('index', '')}\n"
        f"名称：{problem_info.get('name', '')}\n"
        f"rating：{problem_info.get('rating', '')}\n"
        f"tags：{', '.join(problem_info.get('tags', []) or [])}\n\n"
        f"题面：\n{problem_statement[:20000]}"
        f"{tutorial_block}"
    )


def _blocks_to_text(blocks: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for block in blocks:
        block_type = block.get("type", "paragraph")
        text = block.get("text", "")
        if block_type == "image":
            lines.append("[IMG]")  # placeholder for images
        elif block_type == "note":
            lines.append(":::note")
            lines.append(_blocks_to_text(block.get("blocks") or []))
            lines.append(":::")
        elif block_type == "heading":
            lines.append(f"## {text}")
        elif block_type == "pre":
            lines.append("```")
            lines.append(text)
            lines.append("```")
        elif block_type == "list_item":
            lines.append(f"- {text}")
        elif block_type == "ordered_list_item":
            lines.append(f"1. {text}")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def _parse_markdown_blocks(md_text: str) -> list[dict[str, str]]:
    """Parse DeepSeek's markdown output back into our block format."""
    import re

    blocks: list[dict[str, str]] = []
    lines = md_text.strip().splitlines()

    pending_lines: list[str] = []
    in_code_block = False
    code_lines: list[str] = []
    in_note_block = False
    note_lines: list[str] = []

    def flush_pending() -> None:
        nonlocal pending_lines
        if pending_lines:
            blocks.append({"type": "paragraph", "text": "\n".join(pending_lines)})
            pending_lines = []

    for raw_line in lines:
        line = raw_line.rstrip()

        if in_note_block:
            if line.strip() == ":::":
                note_blocks = _parse_markdown_blocks("\n".join(note_lines))
                blocks.append({"type": "note", "blocks": note_blocks})
                note_lines = []
                in_note_block = False
            else:
                note_lines.append(line)
            continue

        if line.strip() == ":::note":
            flush_pending()
            in_note_block = True
            note_lines = []
            continue

        if line.strip() == "[IMG]":
            flush_pending()
            blocks.append({"type": "image", "text": ""})
            continue

        if line.startswith("```"):
            if in_code_block:
                if code_lines:
                    blocks.append({"type": "pre", "text": "\n".join(code_lines)})
                code_lines = []
                in_code_block = False
            else:
                flush_pending()
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+)$", line)
        if heading_match:
            flush_pending()
            blocks.append({"type": "heading", "text": heading_match.group(1).strip()})
            continue

        list_match = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if list_match:
            flush_pending()
            blocks.append({"type": "list_item", "text": list_match.group(1).strip()})
            continue

        ordered_match = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if ordered_match:
            flush_pending()
            blocks.append({"type": "ordered_list_item", "text": ordered_match.group(1).strip()})
            continue

        if not line.strip():
            flush_pending()
            continue

        pending_lines.append(line)

    if in_code_block and code_lines:
        blocks.append({"type": "pre", "text": "\n".join(code_lines)})
    if in_note_block and note_lines:
        blocks.append({"type": "note", "blocks": _parse_markdown_blocks("\n".join(note_lines))})
    flush_pending()

    return blocks
