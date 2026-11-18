"""Per-user problem bookmarks and references to the bot's solution messages."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from bot.services.paths import runtime_data_dir

STAR_DB_PATH = runtime_data_dir() / "stars/stars.sqlite3"
_CF_RE = re.compile(r"([1-9]\d{0,6})([A-Z]\d{0,2})", re.IGNORECASE)
_AT_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", re.IGNORECASE)
_URL_RE = re.compile(r'https?://[^\s<>"，。；）]+', re.IGNORECASE)
_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:CF\s*[1-9]\d{0,6}\s*[A-Z]\d{0,2}|"
    r"AT[_\s]?[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProblemId:
    source: str
    task: str

    @property
    def canonical(self) -> str:
        return ("CF" if self.source == "cf" else "AT_") + self.task

    @property
    def url(self) -> str:
        if self.source == "at":
            return f"https://www.luogu.com.cn/problem/{self.canonical}"
        match = _CF_RE.fullmatch(self.task)
        assert match is not None
        contest, index = match.groups()
        if int(contest) >= 100000:
            return f"https://codeforces.com/gym/{contest}/problem/{index}"
        return f"https://codeforces.com/problemset/problem/{contest}/{index}"


def normalize_problem_id(raw: str) -> ProblemId | None:
    text = raw.strip()
    if len(text) > 250:
        return None
    if re.match(r"https?://", text, re.IGNORECASE):
        return _problem_from_url(text)
    text = re.sub(r"\s+", "", text)
    cf = _CF_RE.fullmatch(text[2:] if text.lower().startswith("cf") else text)
    if cf:
        return ProblemId("cf", cf.group(1) + cf.group(2).upper())
    if text.lower().startswith("cf"):
        return None
    if text.lower().startswith("at_"):
        text = text[3:]
    elif text.lower().startswith("at") and not re.match(r"atc\d", text, re.IGNORECASE):
        text = text[2:]
    if len(text) <= 96 and _AT_RE.fullmatch(text):
        return ProblemId("at", text.lower())
    return None


def _problem_from_url(text: str) -> ProblemId | None:
    try:
        parsed = urlsplit(text)
        if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            return None
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if host in {"codeforces.com", "www.codeforces.com", "mirror.codeforces.com"}:
        match = re.fullmatch(r"/(?:problemset/problem/(\d+)/([A-Za-z]\d*)|(?:contest|gym)/(\d+)/problem/([A-Za-z]\d*))", path)
        if match:
            contest, index = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
            return normalize_problem_id("CF" + contest + index)
    elif host in {"www.luogu.com.cn", "luogu.com.cn"}:
        match = re.fullmatch(r"/problem/(?:solution/)?((?:CF|AT_)[A-Za-z0-9_]+)", path, re.IGNORECASE)
        if match:
            return normalize_problem_id(match.group(1))
    elif host in {"atcoder.jp", "www.atcoder.jp"}:
        match = re.fullmatch(r"/contests/[A-Za-z0-9_-]+/tasks/([A-Za-z0-9_]+)", path)
        if match:
            return normalize_problem_id("AT_" + match.group(1))
    return None


def extract_problem_ids(text: str) -> list[ProblemId]:
    candidates = [match.group(0) for match in _URL_RE.finditer(text)]
    # Remove URLs before looking for identifiers so an unrelated host cannot
    # contribute a lookalike problem ID from its path.
    remainder = _URL_RE.sub(" ", text)
    candidates.extend(match.group(0) for match in _ID_RE.finditer(remainder))
    if not candidates:
        candidates = [text.strip()]
    result: dict[str, ProblemId] = {}
    for candidate in candidates:
        problem = normalize_problem_id(candidate.rstrip(".,;:!?)]}"))
        if problem:
            result[problem.canonical] = problem
    return list(result.values())


def parse_star_args(text: str) -> tuple[str, str]:
    text = text.strip()
    if text[:1] in {"+", "-"}:
        return text[0], text[1:].strip()
    return "+", text


def _connect() -> sqlite3.Connection:
    STAR_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STAR_DB_PATH, timeout=10)
    try:
        connection.execute("""CREATE TABLE IF NOT EXISTS stars (
            user_id TEXT NOT NULL, problem_id TEXT NOT NULL, added_at TEXT NOT NULL,
            PRIMARY KEY (user_id, problem_id)
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS solution_messages (
            bot_id TEXT NOT NULL, message_id TEXT NOT NULL, problem_id TEXT NOT NULL,
            PRIMARY KEY (bot_id, message_id)
        )""")
        return connection
    except Exception:
        connection.close()
        raise


def update_star(user_id: str, problem: ProblemId, *, add: bool) -> bool:
    connection = _connect()
    try:
        with connection:
            if add:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO stars VALUES (?, ?, ?)",
                    (str(user_id), problem.canonical, datetime.now(timezone.utc).isoformat()),
                )
            else:
                cursor = connection.execute("DELETE FROM stars WHERE user_id = ? AND problem_id = ?", (str(user_id), problem.canonical))
            return cursor.rowcount > 0
    finally:
        connection.close()


def list_stars(user_id: str) -> list[ProblemId]:
    connection = _connect()
    try:
        rows = connection.execute("SELECT problem_id FROM stars WHERE user_id = ? ORDER BY added_at, problem_id", (str(user_id),)).fetchall()
        return [problem for (raw,) in rows if (problem := normalize_problem_id(raw)) is not None]
    finally:
        connection.close()


def record_solution_message(bot_id: str, message_id: int | str, problem: ProblemId) -> None:
    connection = _connect()
    try:
        with connection:
            connection.execute("INSERT OR REPLACE INTO solution_messages VALUES (?, ?, ?)", (str(bot_id), str(message_id), problem.canonical))
    finally:
        connection.close()


def solution_message_problem(bot_id: str, message_id: int | str) -> ProblemId | None:
    connection = _connect()
    try:
        row = connection.execute("SELECT problem_id FROM solution_messages WHERE bot_id = ? AND message_id = ?", (str(bot_id), str(message_id))).fetchone()
        return normalize_problem_id(row[0]) if row else None
    finally:
        connection.close()


def format_star_pages(problems: list[ProblemId]) -> list[str]:
    if not problems:
        return ["你的收藏题单为空。使用 /star CF2062A 或 /star AT_arc017_1 添加，也可引用题解消息发送 /star。"]
    pages: list[str] = []
    lines = [f"你的收藏题单（共 {len(problems)} 题）："]
    for index, problem in enumerate(problems, 1):
        line = f"{index}. {problem.canonical}\n{problem.url}"
        if sum(len(item) + 1 for item in lines) + len(line) > 1800:
            pages.append("\n".join(lines))
            lines = ["你的收藏题单（续）："]
        lines.append(line)
    pages.append("\n".join(lines))
    return pages
