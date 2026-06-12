from bot.services.group_config import GroupConfig
from bot.services.help_text import ADMIN_HELP_TEXT, DEFAULT_USER_HELP_TEXT, group_help_text


def test_user_help_does_not_include_admin_commands() -> None:
    assert "/cur <cf|at> <难度>" not in DEFAULT_USER_HELP_TEXT
    assert "/giveup <cf|at> <难度>" not in DEFAULT_USER_HELP_TEXT
    assert "/random <难度>" not in DEFAULT_USER_HELP_TEXT
    assert "/add <uid>" not in DEFAULT_USER_HELP_TEXT
    assert "/remove <uid>" not in DEFAULT_USER_HELP_TEXT
    assert "/emoji <表情" not in DEFAULT_USER_HELP_TEXT
    assert "/emojilist" not in DEFAULT_USER_HELP_TEXT


def test_admin_help_lists_admin_commands() -> None:
    assert "/giveup <cf|at> <难度>" in ADMIN_HELP_TEXT
    assert "/pass <cf|at> <难度>" in ADMIN_HELP_TEXT
    assert "/add <uid>" in ADMIN_HELP_TEXT
    assert "/remove <uid>" in ADMIN_HELP_TEXT
    assert "/emoji <表情或ID>" in ADMIN_HELP_TEXT
    assert "/init <algo:enable|disable>" in ADMIN_HELP_TEXT
    assert "/emojilist" not in ADMIN_HELP_TEXT


def test_group_help_respects_feature_flags() -> None:
    disabled = group_help_text(GroupConfig())
    algo = group_help_text(GroupConfig(algo_enabled=True, rank_mode="all", giveup_count=3, emoji_enabled=False))
    emoji = group_help_text(GroupConfig(algo_enabled=False, emoji_enabled=True))

    assert "/cur <cf|at> <难度>" not in disabled
    assert "/emoji <表情或ID>" not in disabled
    assert "/giveup <cf|at> <难度>" in algo
    assert "3 名群成员" in algo
    assert "/rank - 查看全体排行榜卡片" in algo
    assert "/emoji <表情或ID>" in emoji
