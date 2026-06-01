from bot.services.help_text import ADMIN_HELP_TEXT, USER_HELP_TEXT


def test_user_help_does_not_include_admin_commands() -> None:
    assert "/cur <cf|at> <难度>" in USER_HELP_TEXT
    assert "/giveup <cf|at> <难度>" in USER_HELP_TEXT
    assert "/random <难度>" not in USER_HELP_TEXT
    assert "/add <uid>" not in USER_HELP_TEXT
    assert "/remove <uid>" not in USER_HELP_TEXT


def test_admin_help_lists_admin_commands() -> None:
    assert "/giveup <cf|at> <难度>" in ADMIN_HELP_TEXT
    assert "/pass <cf|at> <难度>" in ADMIN_HELP_TEXT
    assert "/add <uid>" in ADMIN_HELP_TEXT
    assert "/remove <uid>" in ADMIN_HELP_TEXT
