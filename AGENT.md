# AGENT.md — AlgoQuest 维护指南（给 AI/协作者）

这份文档记录项目结构、关键模块、以及判题/搜索的调参方式，便于后续持续维护。面向人类读者的功能说明在 [README.md](README.md)；本文件侧重“代码在哪、怎么改、改了会影响什么”。

## 技术栈与运行

- Python 3.12 + NoneBot2 + OneBot v11 适配器，QQ 侧经 SnowLuma/NapCat 接入。
- 虚拟环境：`.venv/`。跑测试：`.venv/bin/python -m pytest -q`（当前 139 passed）。
- 配置来自项目根目录 `.env`（不入 Git）；`.env.example` 是模板。自定义 `DEEPSEEK_*` 变量由 `bot/services/deepseek.py` 顶部 `load_dotenv(".env")` 显式加载，NoneBot 本身只读自己的配置键。
- 运行数据目录由 `bot/services/paths.py::runtime_data_dir()` 决定，默认项目根 `data/`，可用 `ALGOQUEST_DATA_DIR` 覆盖。

## 目录速查

- `bot/plugins/` — 命令入口（on_command），一个功能一个文件。只做参数解析、权限判断、调用 service、发消息。
- `bot/services/` — 业务逻辑与外部调用。无副作用的纯逻辑尽量放这里，方便测试。
- `tests/` — pytest，用 httpx MockTransport 打桩 DeepSeek，不打真实网络。

## 关键模块

### 渲染管线（题面与搜索共用）

- `bot/services/html_render.py`
  - `build_html(*, title, blocks, subtitle=, meta_items=, footer_text=, ...)` 把结构化 blocks 组装成 MathJax-ready 的 HTML。
  - `render_html_to_png(html, output_path, *, width=960)` 用 Playwright 截图成 PNG，带 `_render_lock` 串行化。
- `bot/services/deepseek.py::_parse_markdown_blocks(md_text)` 把 markdown 文本切成 blocks（heading / paragraph / list_item / pre / note / ...）。这是把任意 DeepSeek markdown 回复变成图片的入口。
- 任何「要把一段 markdown 变成图片」的功能都应复用这三者，不要另写渲染。

### /search 联网搜索

- 入口 `bot/plugins/web_search.py`：解析输入图片 → `search_web()` → 渲染发送。
- 逻辑 `bot/services/web_search.py`：
  - `search_web(raw_query, input_image_urls)` 返回 `SearchReply(text, image_urls)`。
  - `render_search_image(text)` 复用渲染管线输出 PNG，缓存到 `data/search/search-<hash>.png`。插件里 try/except 包裹，渲染失败回退纯文字。
  - 速度分流：`_is_algorithm_question()` 或带图片 → 开 thinking+high，预算 `DEEPSEEK_SEARCH_MAX_TOKENS`；否则关 thinking，预算 `DEEPSEEK_SEARCH_FAST_MAX_TOKENS`（默认 4096）。
  - 时效性：`_answer_system_prompt()` 动态注入当前 UTC+8 日期与「优先最新资料」要求。
  - 要调慢/快或改时效行为，改这两个函数即可，不要动插件层。

### /submit 判题

- 逻辑 `bot/services/submission.py`：
  - 系统提示默认倾向通过（见模块级的中文评审 prompt 常量，`submission.py` 约 499 行「判题目标」段落）。
  - 机械门槛在 `_parse_review_payload()`：只有核心核验项被显式 `FAIL` 才拦截；`UNKNOWN`/空/缺失视为「未被推翻」；阈值 `score ≥ 0.5`、`confidence ≥ 0.5`；`checks` 整体缺失记 UNCERTAIN。
  - 要调宽严度：改 prompt 的倾向描述 + `_parse_review_payload` 的 `core_fail_keys` / 阈值。对应测试在 `tests/test_submission.py`。

## 改动约定

- 新功能优先放 `bot/plugins/`，业务逻辑放 `bot/services/`。
- 改判题/搜索后务必跑 `tests/test_submission.py` 和 `tests/test_web_search.py`。这些测试固化了当前契约，若你有意改契约，同步更新测试并在 commit 里说明。
- 外部调用（DeepSeek、OJ 抓取）一律走 service 层并可配置超时；不要在插件里直接发 HTTP。
- 不要把 API Key、带 token 的图片链接写进日志、聊天或仓库。
- `.env` 不入 Git；新增配置项同时更新 `.env.example` 和 README。
