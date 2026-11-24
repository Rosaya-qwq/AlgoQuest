# AGENT.md — AlgoQuest 维护指南（给 AI/协作者）

这份文档记录项目结构、关键模块、以及判题/题解的调参方式，便于后续持续维护。面向人类读者的功能说明在 [README.md](README.md)；本文件侧重“代码在哪、怎么改、改了会影响什么”。

## 技术栈与运行

- Python 3.12 + NoneBot2 + OneBot v11 适配器，QQ 侧经 SnowLuma/NapCat 接入。
- 虚拟环境：`.venv/`。跑测试：`.venv/bin/python -m pytest -q`。
- 配置来自项目根目录 `.env`（不入 Git）；`.env.example` 是模板。自定义 `DEEPSEEK_*` 变量由 `bot/services/deepseek.py` 顶部 `load_dotenv(".env")` 显式加载，NoneBot 本身只读自己的配置键。
- 运行数据目录由 `bot/services/paths.py::runtime_data_dir()` 决定，默认项目根 `data/`，可用 `ALGOQUEST_DATA_DIR` 覆盖。

## 目录速查

- `bot/plugins/` — 命令入口（on_command），一个功能一个文件。只做参数解析、权限判断、调用 service、发消息。
- `bot/services/` — 业务逻辑与外部调用。无副作用的纯逻辑尽量放这里，方便测试。
- `tests/` — pytest，用 httpx MockTransport 打桩 DeepSeek，不打真实网络。

## 关键模块

### 渲染管线（题面与题解共用）

- `bot/services/html_render.py`
  - `build_html(*, title, blocks, subtitle=, meta_items=, footer_text=, ...)` 把结构化 blocks 组装成 MathJax-ready 的 HTML。
  - `render_html_to_png(html, output_path, *, width=960)` 用 Playwright 截图成 PNG，带 `_render_lock` 串行化。
- `bot/services/deepseek.py::_parse_markdown_blocks(md_text)` 把 markdown 文本切成 blocks（heading / paragraph / list_item / pre / note / ...）。这是把任意 DeepSeek markdown 回复变成图片的入口。
- 任何「要把一段 markdown 变成图片」的功能都应复用这三者，不要另写渲染。

### 参考题解与图片输出

- bot/services/tutorials.py：洛谷登录 Cookie 只从 .env 读取；按 ?orderBy=time 最后一页最后一篇选取，缓存正文与配图。失效时回退已有缓存/官方参考。
- bot/services/solutions.py：复用 Markdown → blocks → HTML → PNG 管线；保留引用配图位置，未引用的参考图放附录。配图缓存与最终 PNG 缓存独立，不记录 Cookie。
- bot/plugins/problem_random.py::send_solution_image()：放弃、提交通过及强制通过共用图片发送。

### /submit 判题

- 逻辑 `bot/services/submission.py`：
  - 系统提示默认倾向通过，仅要求关键构造和证明思路，不要求常规细节。
  - 机械门槛在 `_parse_review_payload()`：只有核心核验项被显式 `FAIL` 才拦截；`UNKNOWN`/空/缺失视为「未被推翻」；阈值 `score ≥ 0.5`、`confidence ≥ 0.5`；`checks` 整体缺失记 UNCERTAIN。
  - 要调宽严度：改 prompt 的倾向描述 + `_parse_review_payload` 的 `core_fail_keys` / 阈值。对应测试在 `tests/test_submission.py`。

### 个人消息与收藏

- `bot/services/message_refs.py`：统一读取事件自带引用或 `get_msg` 返回的 CQ 字符串/消息段数组，不下载附件。
- `bot/services/emoji_rename.py`：沿用原地址/标识，设置 `summary` 和 `sub_type=1`；只构造重发消息，不持久化表情。客户端预览需联机核验。
- `bot/services/stars.py`：校验 CF/AT 题号、解析题号/链接，使用 SQLite 按用户持久化收藏及机器人题解消息关联；多用户独立、重复添加幂等。
- `bot/plugins/problem_random.py::send_solution_image()` 发送成功后记录题号和消息 ID，供纯图片题解的 `/star` 引用识别使用。
- `bot/services/ping.py`：读取同组 `ALGOQUEST_PING_IMAGE_ENABLED/PATH/SUMMARY`，个人图片在 `source/ping.png`，不放进服务器运行数据目录。示例默认关闭，个人 `.env` 可开启。
- 改动以上功能后运行 `tests/test_stars.py`、`tests/test_emoji_rename.py`、`tests/test_ping.py`、`tests/test_personal_commands.py`。

### 一键部署

- `deploy.sh`：Ubuntu/Debian + systemd，托管 Bot/SnowLuma、实时安装输出与 journal；支持只看计划、复用 SnowLuma、明确重置项目 data/venv、卸载托管。
- `deploy.ps1`：Windows WinSW Bot 服务 + 与 QQ 同会话的 SnowLuma 登录计划任务，实时跟随两个程序日志。不能将 QQ bridge 改成 Session 0 服务。
- `scripts/deploy_support.py`：不输出密钥的配置检查、systemd/WinSW 模板、浏览器检查、限定范围的重置。
- `scripts/snowluma_support.py`：官方源失败后使用指定备用 `https://git.hoshizukimio.com/HoshizukiMio/SnowLuma`，完整包选择、SHA-256 校验、安全解包、复用登录目录、WebUI/SSH 链接。
- 安装脚本默认保留 .env、data、source、SnowLuma 登录状态；仅显式 reset 选项可删除项目 data/venv。未运行真实安装时应说明只验证了语法/计划/模板，不能声称已在本机安装服务。
- 改脚本后运行 `tests/test_deployment.py`、`bash -n deploy.sh` 和 PowerShell 解析器检查，避免在开发机安装或停止真实服务来做测试。

## 改动约定

- 新功能优先放 `bot/plugins/`，业务逻辑放 `bot/services/`。
- 改判题/题解后务必跑 `tests/test_submission.py`、`tests/test_tutorials.py` 和 `tests/test_solutions.py`。这些测试固化了当前契约，若你有意改契约，同步更新测试并在 commit 里说明。
- 外部调用（DeepSeek、OJ 抓取）一律走 service 层并可配置超时；不要在插件里直接发 HTTP。
- 不要把 API Key、带 token 的图片链接写进日志、聊天或仓库。
- `.env` 不入 Git；新增配置项同时更新 `.env.example` 和 README。
