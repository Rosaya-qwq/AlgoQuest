from pathlib import Path

from bot.services import group_config
from bot.services.group_config import (
    GroupConfig,
    format_group_config,
    get_group_config,
    group_bot_enabled,
    group_config_exists,
    init_args_to_config,
    parse_init_config_args,
    set_group_config,
)


def test_group_config_defaults_to_disabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(group_config, "GROUP_CONFIG_PATH", tmp_path / "groups.json")

    config = get_group_config("100")

    assert config == GroupConfig()
    assert not group_config_exists("100")
    assert not group_bot_enabled("100")


def test_parse_init_config_args() -> None:
    parsed = parse_init_config_args("algo:enable rank:all giveup:3 emoji:disable")

    assert parsed is not None
    assert init_args_to_config(parsed) == GroupConfig(
        algo_enabled=True,
        rank_mode="all",
        giveup_count=3,
        emoji_enabled=False,
    )
    assert parse_init_config_args("algo:on rank:all giveup:3 emoji:disable") is None
    assert parse_init_config_args("algo:enable rank:all giveup:0 emoji:disable") is None
    assert parse_init_config_args("algo:enable rank:bad giveup:1 emoji:disable") is None


def test_set_and_get_group_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(group_config, "GROUP_CONFIG_PATH", tmp_path / "groups.json")
    config = GroupConfig(algo_enabled=True, rank_mode="self", giveup_count=2, emoji_enabled=True)

    set_group_config("100", config)

    assert group_config_exists("100")
    assert group_bot_enabled("100")
    assert get_group_config("100") == config


def test_format_group_config() -> None:
    text = format_group_config("100", GroupConfig(algo_enabled=True, rank_mode="all", giveup_count=4, emoji_enabled=True))

    assert "群配置：100" in text
    assert "algo:enable" in text
    assert "rank:all" in text
    assert "giveup:4" in text
    assert "emoji:enable" in text
