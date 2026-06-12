from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from nonebot.adapters.onebot.v11 import Event, GroupMessageEvent
from nonebot.log import logger


GROUP_CONFIG_PATH = Path("data/group_config/groups.json")

RankMode = Literal["self", "all"]


@dataclass(frozen=True)
class GroupConfig:
    algo_enabled: bool = False
    rank_mode: RankMode = "self"
    giveup_count: int = 2
    emoji_enabled: bool = False


@dataclass(frozen=True)
class InitConfigArgs:
    algo_enabled: bool
    rank_mode: RankMode
    giveup_count: int
    emoji_enabled: bool


DEFAULT_GROUP_CONFIG = GroupConfig()


def group_id_from_event(event: Event) -> str | None:
    if isinstance(event, GroupMessageEvent):
        return str(event.group_id)
    group_id = getattr(event, "group_id", None)
    return str(group_id) if group_id is not None else None


def get_group_config(group_id: str | int | None) -> GroupConfig:
    if group_id is None:
        return DEFAULT_GROUP_CONFIG
    data = _load_group_configs()
    raw = data.get(str(group_id), {})
    return _normalize_group_config(raw)


def group_config_exists(group_id: str | int | None) -> bool:
    if group_id is None:
        return False
    return str(group_id) in _load_group_configs()


def group_bot_enabled(group_id: str | int | None) -> bool:
    if not group_config_exists(group_id):
        return False
    config = get_group_config(group_id)
    return config.algo_enabled or config.emoji_enabled


def set_group_config(group_id: str | int, config: GroupConfig) -> None:
    data = _load_group_configs()
    data[str(group_id)] = asdict(config)
    _save_group_configs(data)


def parse_init_config_args(text: str) -> InitConfigArgs | None:
    tokens = text.split()
    if len(tokens) != 4:
        return None

    parsed: dict[str, str] = {}
    for token in tokens:
        if ":" not in token:
            return None
        key, value = token.split(":", 1)
        if key in parsed:
            return None
        parsed[key] = value

    if set(parsed) != {"algo", "rank", "giveup", "emoji"}:
        return None

    algo = _parse_enabled(parsed["algo"])
    emoji = _parse_enabled(parsed["emoji"])
    rank = parsed["rank"]
    giveup = parsed["giveup"]
    if algo is None or emoji is None or rank not in {"self", "all"}:
        return None
    if not re.fullmatch(r"\d{1,3}", giveup):
        return None
    giveup_count = int(giveup)
    if giveup_count < 1:
        return None

    return InitConfigArgs(
        algo_enabled=algo,
        rank_mode=rank,  # type: ignore[arg-type]
        giveup_count=giveup_count,
        emoji_enabled=emoji,
    )


def init_args_to_config(args: InitConfigArgs) -> GroupConfig:
    return GroupConfig(
        algo_enabled=args.algo_enabled,
        rank_mode=args.rank_mode,
        giveup_count=args.giveup_count,
        emoji_enabled=args.emoji_enabled,
    )


def format_group_config(group_id: str | int | None, config: GroupConfig) -> str:
    group = str(group_id) if group_id is not None else "private"
    return (
        f"群配置：{group}\n"
        f"algo:{_format_enabled(config.algo_enabled)}\n"
        f"rank:{config.rank_mode}\n"
        f"giveup:{config.giveup_count}\n"
        f"emoji:{_format_enabled(config.emoji_enabled)}"
    )


def algo_enabled_for_event(event: Event) -> bool:
    return get_group_config(group_id_from_event(event)).algo_enabled


def emoji_enabled_for_event(event: Event) -> bool:
    return get_group_config(group_id_from_event(event)).emoji_enabled


def rank_mode_for_event(event: Event) -> RankMode:
    return get_group_config(group_id_from_event(event)).rank_mode


def giveup_count_for_event(event: Event) -> int:
    return get_group_config(group_id_from_event(event)).giveup_count


def _parse_enabled(value: str) -> bool | None:
    if value == "enable":
        return True
    if value == "disable":
        return False
    return None


def _format_enabled(value: bool) -> str:
    return "enable" if value else "disable"


def _normalize_group_config(raw: Any) -> GroupConfig:
    if not isinstance(raw, dict):
        return DEFAULT_GROUP_CONFIG
    rank_mode = raw.get("rank_mode")
    giveup_count = raw.get("giveup_count")
    if rank_mode not in {"self", "all"}:
        rank_mode = DEFAULT_GROUP_CONFIG.rank_mode
    if not isinstance(giveup_count, int) or giveup_count < 1:
        giveup_count = DEFAULT_GROUP_CONFIG.giveup_count
    return GroupConfig(
        algo_enabled=bool(raw.get("algo_enabled", DEFAULT_GROUP_CONFIG.algo_enabled)),
        rank_mode=rank_mode,
        giveup_count=giveup_count,
        emoji_enabled=bool(raw.get("emoji_enabled", DEFAULT_GROUP_CONFIG.emoji_enabled)),
    )


def _load_group_configs() -> dict[str, Any]:
    if not GROUP_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(GROUP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load group config")
        return {}
    if not isinstance(data, dict):
        return {}
    groups = data.get("groups", {})
    return groups if isinstance(groups, dict) else {}


def _save_group_configs(groups: dict[str, Any]) -> None:
    GROUP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    GROUP_CONFIG_PATH.write_text(
        json.dumps({"groups": groups}, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
