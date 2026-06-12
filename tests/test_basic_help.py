from bot.services.group_config import GroupConfig
from bot.services.help_text import admin_help_text, group_help_text


def test_user_help_does_not_include_admin_commands() -> None:
    text = group_help_text(GroupConfig())
    assert "/cur <cf|at> <难度>" not in text
    assert "/giveup <cf|at> <难度>" not in text
    assert "/random <难度>" not in text
    assert "/add <uid>" not in text
    assert "/remove <uid>" not in text
    assert "/emoji <表情" not in text
    assert "/emojilist" not in text


def test_admin_help_lists_admin_commands() -> None:
    text = admin_help_text()
    assert "/giveup <cf|at> <难度>" in text
    assert "/pass <cf|at> <难度>" in text
    assert "/add <uid>" in text
    assert "/remove <uid>" in text
    assert "/emoji <表情或ID>" in text
    assert "/init <algo:enable|disable>" in text
    assert "/emojilist" not in text


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
