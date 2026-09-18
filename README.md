# AlgoQuest

基于 NoneBot2 + SnowLuma 的 QQ 机器人项目。提供 Codeforces / AtCoder 随机算法题与判题功能。

## 作者

<table>
  <tr>
    <td width="92" align="center">
      <a href="https://github.com/Rosaya-qwq">
        <img src="https://github.com/Rosaya-qwq.png?size=160" width="72" height="72" alt="Rosaya-qwq avatar" />
      </a>
    </td>
    <td>
      <strong>Fish Fin Fan</strong><br />
      <sub>@Rosaya-qwq</sub>
    </td>
  </tr>
</table>

- GitHub: [Rosaya-qwq](https://github.com/Rosaya-qwq)
- Email: [fishfinfan@mail.ustc.edu.cn](mailto:fishfinfan@mail.ustc.edu.cn)

## 当前功能

- `/ping`：检查机器人是否在线，返回 `pong`。
- `/help`：查看当前指令和各难度 rating 区间。
- `/giveup <cf|at> <难度>`：在当前群 `algo:enable` 时可用，普通群成员按本群 `giveup:count` 投票放弃当前题；全局超管和本群群管理可直接放弃。放弃后揭示原题名称、链接、rating 和简要题解，然后刷新下一题。仍兼容 `/random`、`随机题` 别名。
- `/add <uid>` / `/remove <uid>`：管理员维护黑名单，黑名单用户不能使用机器人指令。
- `/del <uid>`：超级管理员删除某个用户在榜单中的所有数据。
- `/cur <cf|at> <难度>`：在当前群 `algo:enable` 时可用，重新发送当前难度的题面图片，避免题面被聊天记录刷走。
- `/submit <cf|at> <难度> <题解描述>`：在当前群 `algo:enable` 时可用，提交当前难度题目的题解描述，由 DeepSeek 进行思路评审，并更新本地 rating 与难度计数。
- `/pass <cf|at> <难度>`：在当前群 `algo:enable` 时，本群群管理或全局超管回复用户提交消息，强制通过当前题；不能手动输入 uid，一血已产生时无效。
- `/rank`：在当前群 `algo:enable` 时可用；`rank:self` 时普通用户只能查看自己，`rank:all` 时全体可查看全体排行榜，本群群管理和全局超管始终可查看全体。图片包含头像、用户名、uid、CF/AT rating 和五档难度通过数。
- `/emoji <表情或ID>`：在当前群 `emoji:enable` 时可用；全局超管任意时刻可用。给本条消息贴同款 QQ 表情；如果引用某条消息，则只给被引用的消息贴表情。群成员单独发送一个 Unicode 表情或 QQ 表情时，也会触发跟贴；全局超管发送 Unicode 表情且贴成功后会自动学习绑定。`/emoji 368` 这类数字会直接作为 SnowLuma / OneBot 表情回应 ID 尝试贴上，不可用时返回“表情不可用”。手动给某条消息贴表情时，机器人会尝试给同一条消息贴同款表情；失败时静默。`/emoji <表情>=<ID>` 可以绑定 Unicode 表情与贴表情 ID，`/emoji <表情>!=<ID>` 删除绑定；绑定左侧必须是单个 Unicode 表情，右侧必须全为数字，变体选择符会被规范化去重。未绑定 Unicode 表情会尝试用 Unicode 十进制码点作为 ID，贴成功后自动绑定。
- `/init <algo:enable|disable> <rank:self|all> <giveup:count> <emoji:enable|disable>`：超级管理员覆盖当前群配置。新群默认不可调用 bot，除全局超管外。
- `/config`：超级管理员查看当前群配置。

## DeepSeek AI 评审 / 中文翻译 / LaTeX 公式渲染 启用说明

### LaTeX 公式渲染
**始终启用，无需配置。** 每次刷新新题时自动将 Codeforces 题面中的数学公式渲染为精美数学符号。若用户看到的是旧的缓存题目，管理员重新 `/giveup` 或重启触发预热刷新即可。

### DeepSeek 提交评审

`/submit` 需要配置 `DEEPSEEK_API_KEY`。题面 AI 只做中文翻译，不再做场景混淆。

```env
DEEPSEEK_API_KEY=你的API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_JUDGE_MODEL_CHECK_IN=deepseek-flash
DEEPSEEK_JUDGE_MODEL_EASY=deepseek-flash
DEEPSEEK_JUDGE_MODEL_MEDIUM=deepseek-flash
DEEPSEEK_JUDGE_MODEL_HARD=deepseek-flash
DEEPSEEK_JUDGE_MODEL_IMPOSSIBLE=deepseek-flash
DEEPSEEK_SOLUTION_MODEL_CHECK_IN=deepseek-flash
DEEPSEEK_SOLUTION_MODEL_EASY=deepseek-flash
DEEPSEEK_SOLUTION_MODEL_MEDIUM=deepseek-flash
DEEPSEEK_SOLUTION_MODEL_HARD=deepseek-flash
DEEPSEEK_SOLUTION_MODEL_IMPOSSIBLE=deepseek-flash
DEEPSEEK_TRANSLATION_MODEL=deepseek-flash
DEEPSEEK_TRANSLATION_MODEL_CHECK_IN=deepseek-flash
DEEPSEEK_TRANSLATION_MODEL_EASY=deepseek-flash
DEEPSEEK_TRANSLATION_MODEL_MEDIUM=deepseek-flash
DEEPSEEK_TRANSLATION_MODEL_HARD=deepseek-flash
DEEPSEEK_TRANSLATION_MODEL_IMPOSSIBLE=deepseek-flash
DEEPSEEK_TRANSLATION_ENABLED=true
DEEPSEEK_TIMEOUT_SECONDS=900
DEEPSEEK_MAX_TOKENS=24000
ALGOQUEST_DATA_DIR=
CF_RATING_CHECK_IN=0,1200
CF_RATING_EASY=1200,1800
CF_RATING_MEDIUM=1800,2400
CF_RATING_HARD=2400,3000
CF_RATING_IMPOSSIBLE=3000,inf
AT_RATING_CHECK_IN=0,1200
AT_RATING_EASY=1200,1800
AT_RATING_MEDIUM=1800,2400
AT_RATING_HARD=2400,3000
AT_RATING_IMPOSSIBLE=3000,inf
```

`ALGOQUEST_DATA_DIR` 默认留空即可，此时运行数据固定存放在项目根目录的 `data/` 下，不受 systemd `WorkingDirectory` 影响。只有当你想把榜单、群配置、题目缓存等运行数据单独放到别的磁盘时，才需要填写绝对路径，例如 `/var/lib/algoquest`。

### 个性化文案配置

发布版默认使用 `AlgoQuest` 作为机器人英文名。品牌名和榜单文案可以放在 `.env` 中配置，避免改源码；`/help` 会根据当前群配置自动生成，不再通过 `.env` 覆盖：

```env
NICKNAME=["AlgoQuest","算法练习"]
ALGOQUEST_DISPLAY_NAME=AlgoQuest
ALGOQUEST_RANKLIST_TITLE="{app_name} Ranklist"
ALGOQUEST_RANKLIST_SUBTITLE="Ranked by solved count: IMP/H/M/E/CI."
ALGOQUEST_RANKLIST_FOOTER="Same solved vector shares rank; rating is shown as reference only."
ALGOQUEST_USER_RANK_TITLE="{user_name}'s {app_name} Card"
```

排行榜排序按各难度通过数进行：`impossible -> hard -> medium -> easy -> check-in`。每档数量会补零拼成内部排序键，并按字典序降序排序；排序键只用于排序，不会显示在榜单图片里。五档通过数为 CF 与 AtCoder 的合计，rating 只作为展示信息。启动时会自动修复旧版排行榜数据，把已有 `source_solved_counts` 重新汇总到总通过数。

用法：

```text
/submit cf easy 我的做法是先排序，然后用双指针维护……
```

评审结果会写入：

```text
data/submissions/users.json
```

### 题目难度区间配置

CF 与 AtCoder 的五档随机题区间都从 `.env` 读取，格式是 `min,max`，区间为左闭右开 `[min, max)`；最后一档可以写 `inf`。默认两边保持一致：

```env
CF_RATING_CHECK_IN=0,1200
CF_RATING_EASY=1200,1800
CF_RATING_MEDIUM=1800,2400
CF_RATING_HARD=2400,3000
CF_RATING_IMPOSSIBLE=3000,inf
AT_RATING_CHECK_IN=0,1200
AT_RATING_EASY=1200,1800
AT_RATING_MEDIUM=1800,2400
AT_RATING_HARD=2400,3000
AT_RATING_IMPOSSIBLE=3000,inf
```

### DeepSeek 中文翻译
在 `.env` 中配置以下四项后重启 bot：

```env
DEEPSEEK_API_KEY=你的API Key      # 必填
DEEPSEEK_BASE_URL=https://api.deepseek.com   # 默认值，可改
DEEPSEEK_TRANSLATION_MODEL=deepseek-flash # 题面中文翻译模型
DEEPSEEK_TRANSLATION_ENABLED=true # 设为 true 启用题面中文翻译
```

- `DEEPSEEK_TRANSLATION_ENABLED=false` → 使用英文原始题面
- `DEEPSEEK_TRANSLATION_ENABLED=true` → 只把题面翻译成简体中文，不改变题目背景和本意
- 旧变量 `DEEPSEEK_OBFUSCATION=true` 仍兼容为“启用翻译”，但不会再混淆题面
- API 调用失败时自动回退为原始题面，不影响 `/giveup` 正常使用
- 所有 DeepSeek 调用共用一个异步锁；同一时刻只会发送一个翻译、题解或判题请求，适合 2 核 2G 服务器。
- 翻译、判题和题解在全部难度下统一使用 `deepseek-flash`。旧配置中的 `deepseek-v4-flash` 和 `deepseek-v4-pro` 会自动映射到新模型名，仍建议同步更新服务器 `.env`。
- `DEEPSEEK_BASE_URL` 留空时自动使用 `https://api.deepseek.com`；填写自定义地址时必须包含 `http://` 或 `https://`，且只填写 API 根地址，不要追加 `/chat/completions`。

**首次启用翻译后**，旧缓存题目仍是英文的。执行以下命令清除缓存：

```bash
rm -rf data/codeforces/rendered/* data/codeforces/states/* data/atcoder/rendered/* data/atcoder/states/*
```

### 题库抓取与缓存

Codeforces 和 AtCoder 随机题缓存完全分开：

```text
data/codeforces/problemset.json
data/codeforces/states/
data/codeforces/rendered/
data/atcoder/problemset.json
data/atcoder/states/
data/atcoder/rendered/
data/render_cache_version.json
```

启动时 bot 会先检查现有 `cur_state` 和 `next_state`。如果两个槽位都有有效图片且渲染版本未过期，就直接复用，不会重新随机和渲染；只有缺少题目、图片文件丢失或渲染版本变化时才补题。

每次修改题面渲染机制后，需要在代码中递增 `bot/services/problem_random.py` 里的 `RENDER_VERSION`。下次启动时会自动清空 `states/` 和 `rendered/` 缓存，再重新补齐题目；题库 API 缓存 `problemset.json` 会保留。

AtCoder 题库元数据来自 AtCoder Problems API：

```text
https://kenkoooo.com/atcoder/resources/merged-problems.json
https://kenkoooo.com/atcoder/resources/problem-models.json
```

AtCoder 随机池只保留常规比赛题目，当前 contest id 需要匹配 `abc`、`arc`、`agc` 或 `atc` 前缀；`typical90`、`practice2` 等专题/练习合集不会进入随机。

相关可调参数：

```env
CODEFORCES_HTTP_TIMEOUT_SECONDS=60
ATCODER_HTTP_TIMEOUT_SECONDS=60
TUTORIAL_TIMEOUT_SECONDS=900
TUTORIAL_FETCH_ATTEMPTS=5
PROBLEM_FETCH_RETRY_DELAY_SECONDS=5
PROBLEMSET_FETCH_RETRY_DELAY_SECONDS=10
PROBLEM_FETCH_MAX_ROUNDS=0
PROBLEM_STARTUP_FETCH_MAX_ROUNDS=1
PROBLEM_BUFFER_MAINTENANCE_INTERVAL_SECONDS=60
ATCODER_API_REQUEST_INTERVAL_SECONDS=1.1
CODEFORCES_PROBLEM_PAGE_BASES=https://codeforces.com/problemset/problem,https://mirror.codeforces.com/problemset/problem
CODEFORCES_CONTEST_PAGE_BASES=https://codeforces.com/contest,https://mirror.codeforces.com/contest
CODEFORCES_CLOUDSCRAPER_ENABLED=true
LUOGU_ENABLED=true
LUOGU_HTTP_TIMEOUT_SECONDS=30
VJUDGE_ENABLED=false
VJUDGE_HTTP_TIMEOUT_SECONDS=60
PROBLEM_HTTP_PROXY=
```

- `PROBLEM_FETCH_MAX_ROUNDS=0` 表示题面抓取/渲染失败后持续重试，直到抓到可用题目。
- `PROBLEM_STARTUP_FETCH_MAX_ROUNDS=1` 表示启动时每档最多试一轮，避免 CF 主站/镜像不可用时卡住启动；启动后后台维护任务会继续补题。
- `PROBLEM_BUFFER_MAINTENANCE_INTERVAL_SECONDS` 控制后台补题间隔。只有题目槽位缺失、题面文本为空或 PNG 文件丢失时，后台才会重新抓取并渲染题目。
- 后台维护只会补充缺失或损坏的题面缓存。简要题解 `ai_brief` 属于可选数据，生成失败不会删除题面、换题或在每轮维护中重复调用 DeepSeek，以免配置错误时持续消耗 API 额度。
- `CODEFORCES_CLOUDSCRAPER_ENABLED=true` 表示普通 httpx 抓取 CF 题面失败后，再尝试使用 `cloudscraper` 处理 Cloudflare challenge。它不是万能的；如果 CF 的 challenge 需要真实浏览器交互或当前服务器 IP 被强拦，仍然需要代理或可用镜像。
- `LUOGU_ENABLED=true` 表示 CF/AtCoder 主站题面抓取失败后，尝试解析洛谷搬运页。CF 的回退顺序为主站/镜像/cloudscraper -> 洛谷 -> VJudge，AtCoder 为主站 -> 洛谷。洛谷题面页是公开页面，不需要账号或 Cookie。
- `LUOGU_HTTP_TIMEOUT_SECONDS` 控制单次洛谷题面请求超时。洛谷可能尚未搬运新题；页面不存在、数据为空或解析失败时，该候选会被跳过，随机池自动换一道题继续抓取。
- 洛谷仅作为题面、样例和时空限制的备用来源，不强制抓取洛谷题解。Codeforces 官方 tutorial 获取失败时会直接忽略，不阻塞出题与渲染。
- `VJUDGE_ENABLED=true` 表示 CF 主站、镜像站、cloudscraper 和洛谷都抓取失败后，再用 VJudge 登录态抓取题面描述。VJudge 只作为 Codeforces 题面的最后兜底，不影响 AtCoder 随机池。
- `VJUDGE_HTTP_TIMEOUT_SECONDS` 控制访问 VJudge 页面和题面描述接口的超时时间。
- `PROBLEM_HTTP_PROXY` 只代理 CF、VJudge、洛谷、AtCoder 题库 API、题面和题解抓取，不影响 DeepSeek、SnowLuma、OneBot 或系统中的其他程序。使用 Clash/Mihomo 时通常填写 `http://127.0.0.1:7890`。
- `PROBLEMSET_FETCH_RETRY_DELAY_SECONDS` 控制 CF/AT 题库 API 失败后的重试间隔。
- `ATCODER_API_REQUEST_INTERVAL_SECONDS` 控制连续访问 AtCoder Problems API 的间隔，默认大于 1 秒。

### 使用 Clash/Mihomo 的 Trojan 代理抓取题目

Bot 不能直接把 `trojan://...` 当作 HTTP 代理。正确链路是：

```text
AlgoQuest -> http://127.0.0.1:7890 -> Clash/Mihomo -> Trojan 节点或直连 -> 题目来源站
```

这里推荐服务器使用 Mihomo（Clash.Meta 内核）。代理端口只监听本机回环地址，不要把 `7890` 暴露到公网，也不需要开启 TUN 或全局系统代理。

#### 1. 安装 Mihomo

从官方 Releases 下载与服务器架构匹配的 Linux 版本：

```text
https://github.com/MetaCubeX/mihomo/releases
```

先确认服务器架构：

```bash
uname -m
```

- `x86_64`：选择 `linux-amd64`。
- `aarch64` / `arm64`：选择 `linux-arm64`。

解压后把二进制安装到固定位置。假设解压得到的文件名是 `mihomo`：

```bash
chmod +x mihomo
sudo install -m 755 mihomo /usr/local/bin/mihomo
/usr/local/bin/mihomo -v
```

创建专用用户和目录：

```bash
sudo useradd --system --home-dir /var/lib/mihomo --create-home --shell /usr/sbin/nologin mihomo
sudo install -d -m 750 -o mihomo -g mihomo /etc/mihomo /var/lib/mihomo
```

如果提示 `user 'mihomo' already exists`，可以忽略并继续。

#### 2. 放入 Clash 配置

如果代理服务商提供“Clash 订阅”或可下载的 Clash YAML，优先使用它，不要把订阅 URL、Trojan 密码或完整配置提交到 Git 仓库。将配置保存为：

```text
/etc/mihomo/config.yaml
```

然后确认配置中至少有下面几项；已有同名项时修改原项，不要重复添加：

```yaml
mixed-port: 7890
allow-lan: false
bind-address: 127.0.0.1
mode: rule
log-level: info
```

如果服务商只提供单条 Trojan 节点信息，可以按其给出的服务器、端口、密码、SNI 和传输方式填写。最基础的 TCP Trojan 示例是：

```yaml
mixed-port: 7890
allow-lan: false
bind-address: 127.0.0.1
mode: rule
log-level: info

proxies:
  - name: algoquest-trojan
    type: trojan
    server: 代理服务器域名
    port: 443
    password: "Trojan 密码"
    sni: TLS 证书对应域名
    client-fingerprint: chrome
    udp: true

proxy-groups:
  - name: ALGOQUEST-PROXY
    type: select
    proxies:
      - algoquest-trojan

rules:
  - DOMAIN-SUFFIX,codeforces.com,ALGOQUEST-PROXY
  - DOMAIN-SUFFIX,vjudge.net,ALGOQUEST-PROXY
  - DOMAIN-SUFFIX,atcoder.jp,ALGOQUEST-PROXY
  - DOMAIN-SUFFIX,kenkoooo.com,ALGOQUEST-PROXY
  - DOMAIN-SUFFIX,luogu.com.cn,DIRECT
  - MATCH,DIRECT
```

如果节点使用 WebSocket、gRPC 或 Reality，不能直接套用这个基础示例，应该使用服务商生成的 Clash 配置，因为这些节点还需要额外的传输参数。

限制配置文件权限并检查语法：

```bash
sudo chown mihomo:mihomo /etc/mihomo/config.yaml
sudo chmod 600 /etc/mihomo/config.yaml
sudo -u mihomo /usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml
```

#### 3. 使用 systemd 托管 Mihomo

创建服务：

```bash
sudo nano /etc/systemd/system/mihomo.service
```

写入：

```ini
[Unit]
Description=Mihomo Local Proxy
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=mihomo
Group=mihomo
WorkingDirectory=/var/lib/mihomo
ExecStart=/usr/local/bin/mihomo -d /var/lib/mihomo -f /etc/mihomo/config.yaml
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

启用并查看日志：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mihomo
sudo systemctl status mihomo --no-pager
sudo journalctl -u mihomo -f
```

确认本地代理端口已经监听：

```bash
sudo ss -lntp | grep ':7890'
```

#### 4. 先独立测试代理

检查代理出口是否工作：

```bash
curl -x http://127.0.0.1:7890 -I -L --max-time 30 https://codeforces.com/
curl -x http://127.0.0.1:7890 -I -L --max-time 30 https://vjudge.net/
```

再测试实际 CF 题面：

```bash
curl -x http://127.0.0.1:7890 -sS -L --max-time 30 \
  -o /dev/null -w 'HTTP %{http_code}, total %{time_total}s\n' \
  'https://codeforces.com/problemset/problem/685/E?locale=en'
```

理想结果是 `HTTP 200`。如果仍然是 `403` 且响应头包含 `cf-mitigated: challenge`，说明该代理节点的出口 IP 也被 Cloudflare 验证；在代理服务中换节点后重新测试。

#### 5. 让 AlgoQuest 只对题库使用代理

修改项目 `.env`：

```env
PROBLEM_HTTP_PROXY=http://127.0.0.1:7890
CODEFORCES_PROBLEM_PAGE_BASES=https://codeforces.com/problemset/problem
CODEFORCES_CONTEST_PAGE_BASES=https://codeforces.com/contest
VJUDGE_ENABLED=true
LUOGU_ENABLED=true
```

启用代理后先只保留 CF 主站，避免当前不可达的 `mirror.codeforces.com` 为每次失败额外增加一次完整超时。洛谷通常可从中国大陆服务器直连，因此上面的 Mihomo 规则让它走 `DIRECT`；洛谷失败后 VJudge 仍作为 CF 的最后兜底。

重启并观察日志：

```bash
sudo systemctl restart algorithmic-bot.service
sudo journalctl -u algorithmic-bot.service -f
```

如果实际服务名是 `algoquest.service`，把上面的 `algorithmic-bot.service` 换成 `algoquest.service`。

注意：`cf_clearance` 等 Cloudflare Cookie 通常与浏览器指纹和出口 IP 有关。切换到代理后旧 Cookie 可能失效；如果代理能直接返回题面就不需要 Cookie，否则需要让浏览器使用同一个代理节点重新通过验证，再导出新 Cookie。不要把代理订阅、Trojan 密码或 Cookie 发到公开聊天、写进 README 或提交到 Git。

### CF / AtCoder 登录 Cookie 详细说明

如果服务器抓 CF 题面时日志里出现 `Cloudflare challenge`、`403`、`503`，通常不是 bot 渲染坏了，而是服务器访问 CF 主站或镜像站被拦。可以让 bot 带上你登录后的 Cookie 去访问主站。

方式一：导出 `cookies.txt`

1. 在浏览器里登录 Codeforces 和 AtCoder。
2. 安装浏览器扩展 `Get cookies.txt LOCALLY` 或类似 Cookie 导出工具。
3. 分别打开 `https://codeforces.com` 和 `https://atcoder.jp`，导出 Netscape 格式的 `cookies.txt`。
4. 上传到服务器，例如：

```bash
mkdir -p /home/AlgoQuest/secrets
scp codeforces-cookies.txt root@你的服务器:/home/AlgoQuest/secrets/codeforces-cookies.txt
scp atcoder-cookies.txt root@你的服务器:/home/AlgoQuest/secrets/atcoder-cookies.txt
```

5. 在服务器项目目录的 `.env` 里填写：

```env
CODEFORCES_COOKIES_FILE=/home/AlgoQuest/secrets/codeforces-cookies.txt
ATCODER_COOKIES_FILE=/home/AlgoQuest/secrets/atcoder-cookies.txt
VJUDGE_COOKIES_FILE=/home/AlgoQuest/secrets/vjudge-cookies.txt
CODEFORCES_USER_AGENT=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36
ATCODER_USER_AGENT=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36
VJUDGE_USER_AGENT=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36
```

方式二：Edge 不装插件，直接复制 Cookie 请求头

1. 用 Edge 登录 `https://codeforces.com`。
2. 按 `F12` 打开开发者工具，点 `网络` / `Network`。
3. 刷新页面。
4. 在请求列表里点第一条 `codeforces.com` 的文档请求。
5. 右侧点 `标头` / `Headers`。
6. 找到 `请求标头` / `Request Headers` 里的 `Cookie`。
7. 复制 `Cookie:` 后面的整行内容，填入 `.env`：

```env
CODEFORCES_COOKIE=JSESSIONID=xxx; 39ce7=xxx; cf_clearance=xxx
ATCODER_COOKIE=REVEL_SESSION=xxx
VJUDGE_COOKIE=JSESSIONID=xxx; JSESSlONID=xxx; cf_clearance=xxx
VJUDGE_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0
VJUDGE_ENABLED=true
```

AtCoder 同理，打开 `https://atcoder.jp` 后复制请求里的 `Cookie`，填到 `ATCODER_COOKIE`。

VJudge 同理，登录 `https://vjudge.net` 后复制文档请求里的 `Cookie`，填到 `VJUDGE_COOKIE`；再复制同一个请求的 `User-Agent`，填到 `VJUDGE_USER_AGENT`。VJudge 登录态会过期，过期后日志通常会出现“没有 dataJson”或跳转到登录页，此时重新复制 Cookie 即可。

重启 bot：

```bash
sudo systemctl restart algorithmic-bot.service
```

验证 Cookie 是否有效：

```bash
curl -I -L \
  -A "$CODEFORCES_USER_AGENT" \
  -b /home/AlgoQuest/secrets/codeforces-cookies.txt \
  "https://codeforces.com/problemset/problem/685/E?locale=en"
```

如果还是 `403` 且响应头里有 `cf-mitigated: challenge`，说明当前服务器 IP 仍被 Cloudflare 拦截。此时仅有登录 Cookie 不够，需要在服务器上配置能访问 CF 的代理，或者换一个可用的 CF 题面镜像，并把镜像填到 `CODEFORCES_PROBLEM_PAGE_BASES` / `CODEFORCES_CONTEST_PAGE_BASES`。

验证 VJudge Cookie 是否有效：

```bash
curl -I -L \
  -A "$VJUDGE_USER_AGENT" \
  -H "Cookie: $VJUDGE_COOKIE" \
  "https://vjudge.net/problem/CodeForces-685E"
```

如果返回登录页或 bot 日志提示 VJudge 页面没有 `dataJson`，说明 Cookie 无效、过期或复制不完整。VJudge 当前不能直接当作无登录公开代理使用；未登录访问 `https://vjudge.net/problem/CodeForces-685E` 会跳转到登录页，`/origin` 也会回到 Codeforces 原题页并继续遇到 Cloudflare challenge。

题面备用来源说明：

- CF 题面抓取顺序为：Codeforces 主站/镜像、contest 页面、cloudscraper、洛谷公开题面、VJudge 登录态题面接口。
- AtCoder 题面抓取顺序为：AtCoder 主站、洛谷公开题面。
- 洛谷题面无需登录。直接访问 `https://www.luogu.com.cn/problem/CF1603D` 即可得到公开题目 JSON；洛谷题解页可能要求登录，但 AlgoQuest 不依赖洛谷题解，因此不用配置洛谷账号或 Cookie。
- 洛谷尚未搬运某道题时，bot 会跳过该随机候选并继续抽取下一题，不会把不存在的页面写入缓存。
- VJudge fallback 会把 VJudge 的分段题面 JSON 转成现有 CF 渲染器使用的 `.problem-statement`，并从 VJudge 页面读取时间限制、空间限制和 editorial 链接。

## 本地运行手册

### 1. 先理解整体结构

本项目由两个进程组成：

- SnowLuma：负责接入 QQ 会话，把 QQ 消息转换成 OneBot V11 动作与事件，并提供 WebUI 管理入口。
- NoneBot2：负责运行本项目的 Python 机器人逻辑，收到 `/ping`、`/giveup cf easy`、`/submit at check-in ...` 这类命令后返回结果。

也就是说，机器人 QQ 号不是登录到 NoneBot2 里，而是由 SnowLuma 接入 QQ 会话。NoneBot2 只需要和 SnowLuma 建立 OneBot V11 连接。

本项目推荐使用反向 WebSocket：

```text
QQ <-> SnowLuma <-> ws://127.0.0.1:8080/onebot/v11/ws/ <-> NoneBot2
```

SnowLuma 官方仓库：https://github.com/SnowLuma/SnowLuma

### 2. 准备 NoneBot2 的运行环境

建议使用 Python 3.10 或更高版本。当前项目配置为 `>=3.10,<4.0`。题面 PNG 渲染依赖 Playwright Chromium，中文榜单和题面渲染依赖中文字体。

#### 2.1 Ubuntu / Debian 基础依赖

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip \
  git curl ca-certificates build-essential \
  fontconfig
```

#### 2.2 Python 虚拟环境和项目依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
test -f .env || cp .env.example .env
```

#### 2.3 Playwright Chromium 浏览器

题面会先渲染为 HTML，再用 Playwright 截图为 PNG，因此必须安装 Chromium：

```bash
source .venv/bin/activate
python -m playwright install chromium
```

Linux 服务器如果缺少 Chromium 运行库，再执行：

```bash
sudo .venv/bin/python -m playwright install-deps chromium
```

如果你用 systemd 的 `User=user` 运行服务，建议用同一个用户安装 Playwright 浏览器，否则服务进程可能找不到浏览器缓存：

```bash
sudo -u user /opt/AlgoQuest/.venv/bin/python -m playwright install chromium
```

把 `user` 和 `/opt/AlgoQuest` 换成你的实际用户名和项目路径。

#### 2.4 中文字体安装

推荐安装 Noto CJK 字体和 emoji 字体。它能保证题面、榜单、用户名里的中文和表情符号正常显示，避免服务器上出现乱码或方块字。

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra fonts-noto-color-emoji fonts-dejavu fontconfig
sudo fc-cache -fv
```

RHEL / CentOS / Fedora：

```bash
sudo dnf install -y google-noto-sans-cjk-fonts google-noto-emoji-color-fonts dejavu-sans-fonts dejavu-sans-mono-fonts fontconfig
sudo fc-cache -fv
```

检查字体是否可用：

```bash
fc-match "Noto Sans CJK SC"
fc-match "Noto Color Emoji"
fc-list :lang=zh | head
```

Windows 本地调试通常自带微软雅黑，项目会优先尝试：

```text
C:\Windows\Fonts\msyh.ttc
C:\Windows\Fonts\msyhbd.ttc
```

WSL 会尝试读取：

```text
/mnt/c/Windows/Fonts/msyh.ttc
/mnt/c/Windows/Fonts/msyhbd.ttc
```

### 3. 检查 NoneBot2 配置

默认 `.env` 内容适合本地调试：

```env
DRIVER=~fastapi
HOST=127.0.0.1
PORT=8080
COMMAND_START=["/"]
```

如果你需要指定机器人管理员，把 QQ 号加入 `SUPERUSERS`：

```env
SUPERUSERS=["你的QQ号"]
```

如果你在 SnowLuma 的 OneBot 连接里配置 Access Token，`.env` 中也要设置完全相同的值：

```env
ONEBOT_V11_ACCESS_TOKEN=请换成强随机字符串
```

### 4. 启动 SnowLuma

SnowLuma 是独立程序，不在这个 Python 项目里。它的作用是登录或接入 QQ 会话，并把 QQ 消息按 OneBot V11 协议转发给 NoneBot2。

#### 4.1 下载发行包

前往 SnowLuma Releases 页面下载与你服务器架构匹配的版本：

```text
https://github.com/SnowLuma/SnowLuma/releases
```

官方 README 中的命名规则如下：

```text
Windows x64: SnowLuma-vX.Y.Z-win-x64.zip
Linux x64:   SnowLuma-vX.Y.Z-linux-x64.tar.gz
Linux arm64: SnowLuma-vX.Y.Z-linux-arm64.tar.gz
```

优先下载完整版，完整版内置运行所需 Node.js；Lite 版需要你自己准备 Node.js 22+。

#### 4.2 Windows 启动方式

解压发行包后，运行：

```bat
launcher.bat
```

保持启动窗口运行，然后打开 WebUI。

#### 4.3 Linux 启动方式

解压发行包后进入目录：

```bash
chmod +x launcher.sh
./launcher.sh
```

如果是无人值守服务器，并且你已经阅读并接受 SnowLuma 自身的协议和隐私条款，可以在启动前设置：

```bash
export SNOWLUMA_ACCEPT_EULA=1
export SNOWLUMA_ACCEPT_PRIVACY=1
./launcher.sh
```

这两个变量只用于跳过 WebUI 的协议确认页面，不会写入持久化确认记录。

### 5. 登录或接入机器人 QQ

SnowLuma 启动后，浏览器打开：

```text
http://127.0.0.1:5099
```

初始 WebUI 用户名是：

```text
admin
```

随机密码会打印在 SnowLuma 启动日志里。登录 WebUI 后，按 SnowLuma 页面提示接入已启动的 QQ 进程，并确认机器人 QQ 处于在线状态。

注意事项：

- 建议机器人使用单独 QQ 号，不要直接使用你的主力 QQ。
- 第一次登录或接入可能触发 QQ 设备验证或风控提示，需要按 QQ 客户端提示完成验证。
- `.env` 里的 `SUPERUSERS` 是机器人管理员 QQ 号，不是机器人登录账号。
- SnowLuma 是第三方互操作项目，使用前应阅读其仓库中的 EULA / PRIVACY 说明。

### 6. 启动 NoneBot2

```bash
source .venv/bin/activate
python main.py
```

启动后，NoneBot2 会监听：

```text
ws://127.0.0.1:8080/onebot/v11/ws/
```

启动阶段会检查五个难度的 `cur_state` 和 `next_state` 题目缓存。已有有效缓存时直接复用；缺少缓存、图片文件丢失或 `RENDER_VERSION` 变化时才会重新抓题并完成 PNG 渲染。首次启动或缓存失效时会比普通启动更慢，观察日志中各难度的检查和补题耗时即可。

### 7. 配置 SnowLuma 连接 NoneBot2

在 SnowLuma WebUI 中进入 OneBot 连接配置，添加 WebSocket 客户端，也就是反向 WebSocket：

```text
ws://127.0.0.1:8080/onebot/v11/ws/
```

配置要点：

- 连接类型选择 WebSocket Client / WebSocket 客户端 / 反向 WebSocket。不同版本 UI 文案可能略有差异。
- Access Token 本地调试可以先不填；如果填写，`.env` 中也要设置相同的 `ONEBOT_V11_ACCESS_TOKEN`。
- 保存后启用连接。
- 如果 SnowLuma 和 NoneBot2 不在同一台机器上，URL 里的 `127.0.0.1` 要改成 NoneBot2 所在机器的可访问 IP 或域名。

保存并启用后，QQ 中向机器人发送 `/ping`，如果返回 `pong`，说明链路已打通。

### 8. 推荐启动顺序

本地调试时建议按这个顺序来：

1. 启动 SnowLuma。
2. 在 SnowLuma WebUI 中确认机器人 QQ 已在线。
3. 启动 NoneBot2：

```bash
source .venv/bin/activate
python main.py
```

4. 在 SnowLuma WebUI 中启用 OneBot V11 反向 WebSocket。
5. 用另一个 QQ 给机器人发：

```text
/ping
```

收到 `pong` 即表示成功。

### 9. 常见问题排查

#### 看不到 WebUI 地址

SnowLuma WebUI 默认地址是：

```text
http://127.0.0.1:5099
```

如果打不开，先看 SnowLuma 启动日志，确认实际监听端口和随机管理员密码。

#### WebUI 打不开

检查：

- SnowLuma 进程是否还在运行。
- WebUI 地址和端口是否复制完整。
- 本机浏览器访问本机 SnowLuma 时使用 `127.0.0.1`。
- 远程服务器上的 SnowLuma 不要直接用本机浏览器访问服务器的 `127.0.0.1`，需要 SSH 隧道，见远程部署部分。

#### 反向 WebSocket 连接失败

检查：

- NoneBot2 是否已经启动。
- NoneBot2 日志里是否显示监听 `127.0.0.1:8080`。
- SnowLuma 里填写的 URL 是否完全是：

```text
ws://127.0.0.1:8080/onebot/v11/ws/
```

- 如果配置了 Token，SnowLuma 和 `.env` 中的 Token 必须一致。
- 如果 SnowLuma 在容器里，而 NoneBot2 在宿主机，`127.0.0.1` 可能指向容器自身，需要改成宿主机可访问地址。

#### SnowLuma 提示 `PTRACE_ATTACH ... Operation not permitted`

这表示 SnowLuma 已经找到 QQ 进程，但 Linux 内核拒绝了 Hook 注入。最常见于 SnowLuma 通过 systemd 启动时没有 `CAP_SYS_PTRACE` 权限，或者 QQ 与 SnowLuma 不是同一个 Linux 用户运行。

先确认 QQ 和 SnowLuma 的运行用户。下面的 `814` 替换为日志里的 QQ PID：

```bash
ps -eo user,pid,ppid,cmd | grep -Ei 'qq|snowluma|launcher|node' | grep -v grep
ps -o pid,ppid,user,euser,group,cmd -p 814
```

QQ、SnowLuma 和启动脚本建议都使用同一个普通用户，例如 `ubuntu`，不要一会儿用 `sudo`、一会儿用普通用户启动。修改服务中的 `User`、`Group` 和路径后，确保 SnowLuma 目录可写：

```bash
sudo chown -R ubuntu:ubuntu /home/ubuntu/SnowLuma
sudo chmod -R u+rwX /home/ubuntu/SnowLuma
sudo chmod +x /home/ubuntu/SnowLuma/launcher.sh
```

如果使用下方的 systemd 服务示例，它已经包含最小的 `CAP_SYS_PTRACE` 权限：

```ini
AmbientCapabilities=CAP_SYS_PTRACE
CapabilityBoundingSet=CAP_SYS_PTRACE
```

修改服务后重新加载并重启：

```bash
sudo systemctl daemon-reload
sudo systemctl restart snowluma
sudo journalctl -u snowluma -f
```

如果服务文件中存在下面这一项，请删除或改为 `false`，否则可能禁止 capability 生效：

```ini
NoNewPrivileges=true
```

仍然失败时，检查系统的 Yama ptrace 限制：

```bash
cat /proc/sys/kernel/yama/ptrace_scope
```

可以先临时放开限制验证问题：

```bash
sudo sysctl -w kernel.yama.ptrace_scope=0
sudo systemctl restart snowluma
```

确认确实是该限制导致后，如需永久保留：

```bash
sudo nano /etc/sysctl.d/99-snowluma-ptrace.conf
```

写入：

```conf
kernel.yama.ptrace_scope = 0
```

应用配置：

```bash
sudo sysctl --system
```

成功后 SnowLuma 日志应重新出现：

```text
[Hook] pipe connected: PID=...
```

如果 QQ 或 SnowLuma 运行在 Docker 容器中，还需要在创建容器时增加 `SYS_PTRACE` capability；仅修改宿主机的 `ptrace_scope` 可能不够。

#### QQ 发了 `/ping` 没反应

检查：

- 发送对象是不是机器人 QQ，而不是你自己的 QQ。
- 机器人 QQ 是否仍然在线。
- SnowLuma 是否收到了消息。
- NoneBot2 控制台是否有收到事件日志。
- 命令前缀是否是 `/`，当前只配置了斜杠命令。

## 远程服务器部署手册

### 1. 服务器基础环境

建议准备：

- Linux 服务器，推荐 Ubuntu 22.04/24.04 或 Debian 12。
- Python 3.10+。
- 可长期运行 SnowLuma 的环境。
- 一个专门运行机器人的普通用户，不建议直接使用 `root` 长期运行。

### 2. 从零 SSH 连接服务器

下面假设服务器公网 IP 是 `1.2.3.4`，登录用户是 `root`。如果你的云厂商给的是普通用户，例如 `ubuntu`、`debian`、`ecs-user`，把命令里的 `root` 换成实际用户名。

#### 2.1 确认服务器连接信息

在云服务器控制台确认：

- 公网 IP 或域名。
- SSH 端口，默认是 `22`。
- 登录用户名。
- 登录方式：密码登录或 SSH 密钥登录。
- 安全组/防火墙已放行 TCP `22` 端口。

#### 2.2 第一次尝试连接

默认端口：

```bash
ssh root@1.2.3.4
```

非默认端口，例如 `2222`：

```bash
ssh -p 2222 root@1.2.3.4
```

第一次连接时会看到主机指纹确认，输入 `yes`。如果服务器允许密码登录，随后输入服务器登录密码。

#### 2.3 使用 SSH 密钥登录

如果本机还没有 SSH key，先生成一个：

```bash
ssh-keygen -t ed25519 -C "algoquest"
```

一路回车即可。默认会生成：

```text
~/.ssh/id_ed25519
~/.ssh/id_ed25519.pub
```

把公钥加入服务器。服务器支持密码登录时，可以用：

```bash
ssh-copy-id root@1.2.3.4
```

如果 `ssh-copy-id` 不可用，就手动查看本机公钥：

```bash
cat ~/.ssh/id_ed25519.pub
```

复制输出内容，在云服务器控制台的 SSH 密钥管理里绑定到服务器，或登录服务器后追加到：

```text
~/.ssh/authorized_keys
```

之后用密钥连接：

```bash
ssh -i ~/.ssh/id_ed25519 root@1.2.3.4
```

#### 2.4 常见 SSH 报错

`Permission denied (publickey)` 表示服务器要求密钥登录，但你当前没有提供可用私钥。按顺序检查：

- 云服务器控制台是否已经给这台机器绑定了你的公钥。
- 本机是否使用了正确私钥：`ssh -i ~/.ssh/id_ed25519 root@1.2.3.4`。
- 用户名是否正确，很多镜像默认不是 `root`，而是 `ubuntu`、`debian` 或 `ecs-user`。
- 服务器安全组是否放行 SSH 端口。
- 如果你改过 SSH 端口，命令里是否加了 `-p 端口号`。

可以加 `-v` 查看 SSH 具体用了哪些 key：

```bash
ssh -v -i ~/.ssh/id_ed25519 root@1.2.3.4
```

`Connection timed out` 通常是 IP、端口、安全组或服务器防火墙问题。

`Host key verification failed` 通常是服务器重装后主机指纹变化。确认服务器确实是你的机器后，删除旧记录再连接：

```bash
ssh-keygen -R 1.2.3.4
ssh root@1.2.3.4
```

#### 2.5 通过 SSH 隧道打开 SnowLuma WebUI

服务器上的 SnowLuma WebUI 通常只监听服务器自己的 `127.0.0.1:5099`。本机浏览器不能直接访问服务器的 `127.0.0.1`，需要开 SSH 端口转发：

```bash
ssh -L 5099:127.0.0.1:5099 root@1.2.3.4
```

保持这个 SSH 窗口不要关闭，然后在本机浏览器打开：

```text
http://127.0.0.1:5099
```

如果 SnowLuma 日志里显示的端口不是 `5099`，就把两处端口都改成日志里的实际端口：

```bash
ssh -L 5100:127.0.0.1:5100 root@1.2.3.4
```

如果服务器 SSH 端口不是 `22`，同时加 `-p`：

```bash
ssh -p 2222 -L 5099:127.0.0.1:5099 root@1.2.3.4
```

### 3. 上传项目

将项目上传到服务器，例如：

```bash
scp -r AlgoQuest user@server:/opt/AlgoQuest
```

已有服务器目录时，推荐用 `rsync` 增量同步代码，并保留服务器本地的 `.env`、`.venv` 和运行数据：

```bash
rsync -az --delete \
  --exclude '.venv/' --exclude '.env' --exclude 'data/' --exclude '__pycache__/' \
  ./ user@server:/opt/AlgoQuest/
```

进入项目目录并安装依赖：

```bash
cd /opt/AlgoQuest
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip \
  git curl ca-certificates build-essential \
  fontconfig fonts-noto-cjk fonts-noto-cjk-extra fonts-dejavu
sudo fc-cache -fv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
python -m playwright install chromium
test -f .env || cp .env.example .env
```

如果 Playwright 提示服务器缺少 Chromium 运行库，再执行：

```bash
sudo .venv/bin/python -m playwright install-deps chromium
```

如果后续用 systemd 的 `User=user` 运行 bot，浏览器最好也用同一个用户安装：

```bash
sudo -u user /opt/AlgoQuest/.venv/bin/python -m playwright install chromium
```

### 4. 在服务器安装并启动 SnowLuma

从 SnowLuma Releases 下载 Linux 发行包，推荐完整版：

```text
https://github.com/SnowLuma/SnowLuma/releases
```

上传或直接下载到服务器后，解压到固定目录，例如：

```bash
sudo mkdir -p /opt/SnowLuma
sudo tar -xzf SnowLuma-vX.Y.Z-linux-x64.tar.gz -C /opt/SnowLuma --strip-components=1
cd /opt/SnowLuma
chmod +x launcher.sh
```

启动：

```bash
SNOWLUMA_ACCEPT_EULA=1 SNOWLUMA_ACCEPT_PRIVACY=1 ./launcher.sh
```

如果你不想用环境变量跳过确认，就直接执行 `./launcher.sh`，然后进入 WebUI 完成确认。

建议后续也给 SnowLuma 单独做 systemd 服务或 tmux/screen 托管，确保 SSH 断开后进程不会退出。

### 5. 修改服务端配置

如果 SnowLuma 和 NoneBot2 在同一台服务器上，可以继续使用：

```env
HOST=127.0.0.1
PORT=8080
```

如果 SnowLuma 在另一台机器上，需要让 NoneBot2 监听外部地址：

```env
HOST=0.0.0.0
PORT=8080
ONEBOT_V11_ACCESS_TOKEN=请换成强随机字符串
```

同时在服务器安全组或防火墙中只放行必要来源 IP，避免把无 Token 的 OneBot 入口暴露到公网。

### 6. 服务器 SnowLuma 连接地址

同机部署：

```text
ws://127.0.0.1:8080/onebot/v11/ws/
```

跨机器部署：

```text
ws://服务器IP或域名:8080/onebot/v11/ws/
```

跨机器部署时建议配置 Access Token，并确保 SnowLuma 和 `.env` 中的 Token 一致。

### 7. 服务器接入机器人 QQ

服务器上同样是 SnowLuma 负责接入机器人 QQ。常见流程是：

1. 在服务器启动 SnowLuma。
2. 查看 SnowLuma 日志中的 WebUI 随机管理员密码。
3. 如果 WebUI 只监听 `127.0.0.1`，可以用 SSH 端口转发在本机浏览器打开：

```bash
ssh -L 5099:127.0.0.1:5099 user@server
```

然后访问：

```text
http://127.0.0.1:5099
```

4. 在 WebUI 中接入机器人 QQ，并确认账号在线。
5. 登录完成后，再添加并启用 OneBot V11 反向 WebSocket 连接。

不要把 SnowLuma WebUI 直接无保护暴露到公网；如果必须远程访问，至少使用防火墙、反向代理认证或 SSH 隧道。

### 8. 使用 systemd 托管 NoneBot2

创建服务文件：

```bash
sudo nano /etc/systemd/system/algoquest.service
```

填入：

```ini
[Unit]
Description=AlgoQuest NoneBot2 Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/AlgoQuest
ExecStart=/opt/AlgoQuest/.venv/bin/python /opt/AlgoQuest/main.py
Restart=always
RestartSec=5
User=user
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

把 `User=user` 和 `/opt/AlgoQuest` 替换为你的实际用户和路径，然后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now algoquest
sudo systemctl status algoquest
```

查看日志：

```bash
journalctl -u algoquest -f
```

### 9. 使用 systemd 托管 SnowLuma

如果你把 SnowLuma 放在 `/opt/SnowLuma`，可以创建服务文件：

```bash
sudo nano /etc/systemd/system/snowluma.service
```

填入：

```ini
[Unit]
Description=SnowLuma QQ OneBot Bridge
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/SnowLuma
ExecStart=/opt/SnowLuma/launcher.sh
Restart=always
RestartSec=5
Environment=HOME=/home/ubuntu
Environment=SNOWLUMA_ACCEPT_EULA=1
Environment=SNOWLUMA_ACCEPT_PRIVACY=1
AmbientCapabilities=CAP_SYS_PTRACE
CapabilityBoundingSet=CAP_SYS_PTRACE

[Install]
WantedBy=multi-user.target
```

把 `ubuntu`、`/home/ubuntu` 和 `/opt/SnowLuma` 换成你的实际用户及安装路径。QQ 和 SnowLuma 必须使用同一个 Linux 用户运行；如果服务中配置了 `NoNewPrivileges=true`，请删除该行。启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now snowluma
sudo systemctl status snowluma
```

查看 SnowLuma 日志：

```bash
journalctl -u snowluma -f
```

### 10. 使用脚本更新 SnowLuma

项目根目录提供了 `update_snowluma.sh`。脚本会自动读取 GitHub 最新正式版、识别 `x86_64` / `arm64`、下载对应的 Linux 完整版并校验 GitHub Release 提供的 SHA-256。更新前会创建完整备份，保留配置、登录状态、日志和数据库；如果新服务无法启动，会自动回滚。

先把脚本随项目同步到服务器，然后赋予执行权限：

```bash
cd /opt/AlgoQuest
chmod +x update_snowluma.sh
```

如果 SnowLuma 安装在 `/opt/SnowLuma`，服务名是 `snowluma.service`，直接执行：

```bash
sudo ./update_snowluma.sh
```

如果 SnowLuma 安装在此前使用的 `/home/ubuntu/SnowLuma`：

```bash
sudo ./update_snowluma.sh \
  --install-dir /home/ubuntu/SnowLuma \
  --service snowluma.service \
  --owner ubuntu:ubuntu
```

只检查当前版和最新版，不执行更新：

```bash
./update_snowluma.sh --check --install-dir /home/ubuntu/SnowLuma
```

安装指定版本或强制重装当前版本：

```bash
sudo ./update_snowluma.sh --version v1.14.17
sudo ./update_snowluma.sh --force
```

如果服务器直连 GitHub 下载发行包很慢，而本机 Mihomo 已监听 `7890`，只让本次更新经过代理：

```bash
sudo ./update_snowluma.sh --proxy http://127.0.0.1:7890
```

也可以使用环境变量 `SNOWLUMA_DOWNLOAD_PROXY`。代理只用于读取 GitHub Release 信息和下载压缩包。

默认保留最近 3 份备份，位置是 SnowLuma 安装目录同级的 `snowluma-backups/`。可以调整数量和路径：

```bash
sudo ./update_snowluma.sh \
  --keep 5 \
  --backup-dir /home/ubuntu/snowluma-backups
```

更新完成后检查：

```bash
sudo systemctl status snowluma --no-pager
sudo journalctl -u snowluma -n 100 --no-pager
```

脚本只更新 SnowLuma，不会更新或重启 QQ 客户端。SnowLuma 重启期间 OneBot WebSocket 会短暂断开，恢复后 NoneBot2 会自动重新连接。不要在 SnowLuma 正在更新时手动运行另一份 `launcher.sh`。

### 11. 服务器推荐启动顺序

服务器上建议按这个顺序确认：

1. 启动 SnowLuma。
2. 通过 SSH 隧道打开 SnowLuma WebUI。
3. 接入机器人 QQ 并确认在线。
4. 启动或重启 NoneBot2 systemd 服务：

```bash
sudo systemctl restart algoquest
sudo systemctl status algoquest
```

5. 在 SnowLuma WebUI 中启用 OneBot V11 反向 WebSocket。
6. 用另一个 QQ 发送 `/ping`。
7. 如果没有返回，分别查看 NoneBot2 和 SnowLuma 日志：

```bash
journalctl -u algoquest -f
journalctl -u snowluma -f
```

## 后续功能开发约定

- 新功能优先放在 `bot/plugins/` 下，按功能拆分插件。
- 随机题和提交评审功能后续建议拆成题库服务、提交解析、沙箱评测、结果回传四部分，避免全部塞进一个插件。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。

## 参考文档

- NoneBot2 文档：https://nonebot.dev/
- NoneBot OneBot 适配器文档：https://onebot.adapters.nonebot.dev/
- SnowLuma 文档与 Releases：https://github.com/SnowLuma/SnowLuma
- AtCoder Problems API：https://github.com/kenkoooo/AtCoderProblems/blob/master/doc/api.md
