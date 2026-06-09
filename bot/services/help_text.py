from __future__ import annotations

from bot.services.branding import app_name, env_text


DEFAULT_USER_HELP_TEXT = """{app_name}
/ping - 检查机器人是否在线
/cur <cf|at> <难度> - 重新发送当前题面
/submit <cf|at> <难度> <题解描述> - 提交题解描述并由 AI 评审
/giveup <cf|at> <难度> - 投票放弃当前题，两名群成员同意后刷新
/rank - 查看自己的解题排行榜卡片
/help - 查看当前指令"""


DEFAULT_ADMIN_HELP_TEXT = """/giveup <cf|at> <难度> - 立即放弃当前题，揭示原题与简要题解，并刷新下一题
/rank - 查看全体成员排行榜，群管理也可用
/pass <cf|at> <难度> - 管理员回复用户提交消息，强制当前题通过并按 /submit 通过计分
/add <uid> - 将用户加入黑名单
/remove <uid> - 将用户移出黑名单
/del <uid> - 超级管理员删除某个用户的榜单数据
/emoji <表情或ID> - 超级管理员给本条消息或被引用消息贴同款 QQ 表情
/emojilist - 超级管理员查看已学习的贴表情 ID"""


REQUIRED_ADMIN_HELP_LINES = (
    "/emoji <表情或ID> - 超级管理员给本条消息或被引用消息贴同款 QQ 表情",
    "/emojilist - 超级管理员查看已学习的贴表情 ID",
)


def user_help_text() -> str:
    return env_text("ALGOQUEST_USER_HELP_TEXT", DEFAULT_USER_HELP_TEXT).format(app_name=app_name())


def admin_help_text() -> str:
    text = env_text("ALGOQUEST_ADMIN_HELP_TEXT", DEFAULT_ADMIN_HELP_TEXT).format(app_name=app_name())
    for line in REQUIRED_ADMIN_HELP_LINES:
        if line not in text:
            text = f"{text.rstrip()}\n{line}"
    return text


USER_HELP_TEXT = user_help_text()
ADMIN_HELP_TEXT = admin_help_text()
