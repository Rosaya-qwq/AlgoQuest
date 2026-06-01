# AlgoQuest

基于 NoneBot2 + NapCatQQ 的 QQ 机器人项目。提供 Codeforces / AtCoder 随机算法题与判题功能。

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
- `/giveup <cf|at> <难度>`：普通群成员两人投票放弃当前题；管理员和群管理可直接放弃。放弃后揭示原题名称、链接、rating 和简要题解，然后刷新下一题。仍兼容 `/random`、`随机题` 别名。
- `/add <uid>` / `/remove <uid>`：管理员维护黑名单，黑名单用户不能使用机器人指令。
- `/cur <cf|at> <难度>`：重新发送当前难度的题面图片，避免题面被聊天记录刷走。
- `/submit <cf|at> <难度> <题解描述>`：提交当前难度题目的题解描述，由 DeepSeek 进行思路评审，并更新本地 rating 与难度计数。
- `/pass <cf|at> <难度> [uid]`：管理员、群管理或 rating 高于本题难度上界的用户可强制通过当前题，一血已产生时无效。
- `/rank`：管理员和群管理查看全体成功解题用户排行榜；普通用户只能查看自己的排名卡片。图片包含头像、用户名、uid、CF/AT rating 和五档难度通过数。

## DeepSeek AI 评审 / 混淆 / LaTeX 公式渲染 启用说明

### LaTeX 公式渲染
**始终启用，无需配置。** 每次刷新新题时自动将 Codeforces 题面中的数学公式渲染为精美数学符号。若用户看到的是旧的缓存题目，管理员重新 `/giveup` 或重启触发预热刷新即可。

### DeepSeek 提交评审

`/submit` 需要配置 `DEEPSEEK_API_KEY`。它不要求启用 `DEEPSEEK_OBFUSCATION`。

```env
DEEPSEEK_API_KEY=你的API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_JUDGE_MODEL_CHECK_IN=deepseek-v4-flash
DEEPSEEK_JUDGE_MODEL_EASY=deepseek-v4-flash
DEEPSEEK_JUDGE_MODEL_MEDIUM=deepseek-v4-flash
DEEPSEEK_JUDGE_MODEL_HARD=deepseek-v4-flash
DEEPSEEK_JUDGE_MODEL_IMPOSSIBLE=deepseek-v4-pro
DEEPSEEK_SOLUTION_MODEL_CHECK_IN=deepseek-v4-flash
DEEPSEEK_SOLUTION_MODEL_EASY=deepseek-v4-flash
DEEPSEEK_SOLUTION_MODEL_MEDIUM=deepseek-v4-flash
DEEPSEEK_SOLUTION_MODEL_HARD=deepseek-v4-flash
DEEPSEEK_SOLUTION_MODEL_IMPOSSIBLE=deepseek-v4-pro
DEEPSEEK_TRANSLATION_MODEL=deepseek-v4-flash
DEEPSEEK_TRANSLATION_MODEL_CHECK_IN=deepseek-v4-flash
DEEPSEEK_TRANSLATION_MODEL_EASY=deepseek-v4-flash
DEEPSEEK_TRANSLATION_MODEL_MEDIUM=deepseek-v4-flash
DEEPSEEK_TRANSLATION_MODEL_HARD=deepseek-v4-flash
DEEPSEEK_TRANSLATION_MODEL_IMPOSSIBLE=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=600
DEEPSEEK_MAX_TOKENS=12000
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

### 个性化文案配置

发布版默认使用 `AlgoQuest` 作为机器人英文名。所有本地个性化文案都可以放在 `.env` 中配置，避免改源码：

```env
NICKNAME=["AlgoQuest","算法练习"]
ALGOQUEST_DISPLAY_NAME=AlgoQuest
ALGOQUEST_USER_HELP_TEXT="{app_name}\n/ping - 检查机器人是否在线\n/cur <cf|at> <难度> - 重新发送当前题面\n/submit <cf|at> <难度> <题解描述> - 提交题解描述并由 AI 评审\n/giveup <cf|at> <难度> - 投票放弃当前题，两名群成员同意后刷新\n/rank - 查看自己的解题排行榜卡片\n/help - 查看当前指令"
ALGOQUEST_ADMIN_HELP_TEXT="/giveup <cf|at> <难度> - 立即放弃当前题，揭示原题与简要题解，并刷新下一题\n/rank - 查看全体成员排行榜，群管理也可用\n/pass <cf|at> <难度> [uid] - 强制当前题通过并按 /submit 通过计分\n/add <uid> - 将用户加入黑名单\n/remove <uid> - 将用户移出黑名单"
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

### DeepSeek 混淆 + 中文翻译
在 `.env` 中配置以下四项后重启 bot：

```env
DEEPSEEK_API_KEY=你的API Key      # 必填
DEEPSEEK_BASE_URL=https://api.deepseek.com   # 默认值，可改
DEEPSEEK_TRANSLATION_MODEL=deepseek-v4-flash # 题面混淆 + 中文翻译模型
DEEPSEEK_OBFUSCATION=true         # 设为 true 启用
```

- `DEEPSEEK_OBFUSCATION=false` → 使用英文原始题面（无混淆）
- `DEEPSEEK_OBFUSCATION=true` → 场景混淆 + 中文翻译 + AI 解析摘要
- API 调用失败时自动回退为原始题面，不影响 `/giveup` 正常使用
- 所有 DeepSeek 调用共用一个异步锁；同一时刻只会发送一个翻译、题解或判题请求，适合 2 核 2G 服务器。
- 默认只有 `impossible` 难度的判题和题解使用 `deepseek-v4-pro`，其他难度和全部翻译使用 `deepseek-v4-flash`。

**首次启用混淆后**，旧缓存题目仍是英文/无混淆的。执行以下命令清除缓存：

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
TUTORIAL_TIMEOUT_SECONDS=600
TUTORIAL_FETCH_ATTEMPTS=3
PROBLEM_FETCH_RETRY_DELAY_SECONDS=5
PROBLEMSET_FETCH_RETRY_DELAY_SECONDS=10
PROBLEM_FETCH_MAX_ROUNDS=0
ATCODER_API_REQUEST_INTERVAL_SECONDS=1.1
```

- `PROBLEM_FETCH_MAX_ROUNDS=0` 表示题面抓取/渲染失败后持续重试，直到抓到可用题目。
- `PROBLEMSET_FETCH_RETRY_DELAY_SECONDS` 控制 CF/AT 题库 API 失败后的重试间隔。
- `ATCODER_API_REQUEST_INTERVAL_SECONDS` 控制连续访问 AtCoder Problems API 的间隔，默认大于 1 秒。

## 本地运行手册

### 1. 先理解整体结构

本项目由两个进程组成：

- NapCatQQ：负责登录 QQ、接收 QQ 消息、把消息按 OneBot V11 协议转发出来。
- NoneBot2：负责运行我们的 Python 机器人逻辑，收到 `/ping`、`/giveup cf easy`、`/submit at check-in ...` 这类命令后返回结果。

也就是说，机器人 QQ 号不是登录到 NoneBot2 里，而是登录到 NapCatQQ 里。NoneBot2 只需要和 NapCatQQ 建立 OneBot V11 连接。

本项目推荐使用反向 WebSocket：

```text
QQ <-> NapCatQQ <-> ws://127.0.0.1:8080/onebot/v11/ws/ <-> NoneBot2
```

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

推荐安装 Noto CJK 字体。它能保证题面、榜单、用户名里的中文正常显示，避免服务器上出现乱码或方块字。

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra fonts-dejavu fontconfig
sudo fc-cache -fv
```

RHEL / CentOS / Fedora：

```bash
sudo dnf install -y google-noto-sans-cjk-fonts dejavu-sans-fonts dejavu-sans-mono-fonts fontconfig
sudo fc-cache -fv
```

检查字体是否可用：

```bash
fc-match "Noto Sans CJK SC"
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

### 4. 启动 NapCatQQ

NapCatQQ 是独立程序，不在这个 Python 项目里。你需要先根据自己的系统安装并启动 NapCatQQ。

推荐选择：

- Windows 本地调试：使用 NapCat Windows 一键包，最省事。
- Linux 本地或服务器：优先使用官方 Linux 一键脚本的 Shell 方式。
- 已经熟悉 Docker：可以使用 Docker 方式，迁移和重启比较方便。

#### 4.1 Windows 启动方式

适合你在 Windows 桌面上先调试机器人。

1. 打开 NapCatQQ Releases 页面：

```text
https://github.com/NapNeko/NapCatQQ/releases
```

2. 下载 Windows 一键包或 Shell 包。通常优先选：

```text
NapCat.Shell.Windows.OneKey.zip
```

3. 解压到一个固定目录，例如：

```text
D:\Bot\NapCatQQ
```

4. 进入解压后的目录，先运行安装器或启动脚本。不同版本文件名可能略有变化，常见入口包括：

```text
NapCatInstaller.exe
napcat.bat
launcher.bat
launcher-win10.bat
```

5. 如果你使用 Shell 包，也可以用 QQ 号作为快速登录参数。这个参数只是告诉 NapCatQQ 要登录哪个账号，不是密码：

```bat
launcher.bat 123456789
```

Windows 10 可尝试：

```bat
launcher-win10.bat 123456789
```

6. 启动后不要关闭窗口，观察终端日志。日志里会出现 WebUI 地址，通常类似：

```text
http://127.0.0.1:6099/webui?token=xxxxxxxx
```

7. 用浏览器打开这个 WebUI 地址，进入 QQ 登录页面，使用手机 QQ 扫码登录机器人 QQ。

#### 4.2 Linux Shell 启动方式

适合 Ubuntu、Debian、CentOS 等 Linux 系统，也是后续服务器部署最常用的方式。

1. 安装基础工具：

```bash
sudo apt update
sudo apt install -y curl ca-certificates
```

2. 下载并运行官方 Linux 一键脚本：

```bash
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
bash napcat.sh
```

3. 如果你希望进入可视化交互安装界面，可以用：

```bash
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
bash napcat.sh --tui
```

4. 如果你希望安装 Shell 方式并带 TUI-CLI 管理工具，可以用：

```bash
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
bash napcat.sh --docker n --cli y
```

5. 安装完成后，按照脚本输出启动 NapCatQQ。不同安装方式输出的启动命令可能不同，优先以安装脚本最后打印的命令为准。

6. 如果安装了 TUI-CLI，可以尝试进入管理界面：

```bash
sudo napcat
```

7. 启动成功后查看终端日志，找到 WebUI 地址，通常类似：

```text
http://127.0.0.1:6099/webui?token=xxxxxxxx
```

如果端口 `6099` 被占用，NapCatQQ 可能会自动尝试 `6100`、`6101` 等端口，实际地址以启动日志为准。

#### 4.3 Linux Docker 启动方式

适合你已经熟悉 Docker，或者希望后续迁移服务器时更容易复现环境。

1. 确保服务器已安装 Docker。

2. 使用官方安装脚本走 Docker 安装：

```bash
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
bash napcat.sh --docker y --qq "123456789" --mode ws --proxy 1 --confirm
```

把 `123456789` 换成机器人 QQ 号。

3. Docker 方式下，NoneBot2 和 NapCatQQ 的地址要看它们是否在同一个网络里：

- 如果 NoneBot2 跑在宿主机，NapCatQQ 容器要能访问宿主机的 `8080` 端口。
- 如果 NoneBot2 和 NapCatQQ 都跑在 Docker Compose 同一网络里，反向 WebSocket 地址通常应写服务名，而不是 `127.0.0.1`。

本项目当前先按本地非 Docker 的 NoneBot2 来配置，地址使用：

```text
ws://127.0.0.1:8080/onebot/v11/ws/
```

如果后续把 NoneBot2 也容器化，再单独调整这部分。

### 5. 登录机器人 QQ

NapCatQQ 启动后：

1. 打开启动日志里显示的 WebUI 地址，例如：

```text
http://127.0.0.1:6099/webui?token=xxxxxxxx
```

2. 如果地址里没有带 token，就根据日志里的 token 登录；也可以查看 NapCatQQ 的 `webui.json` 配置文件。

3. 进入 WebUI 后，找到 QQ 登录入口，选择二维码登录。

4. 用手机 QQ 扫码，登录你准备用作机器人的 QQ 号。

5. 登录成功后，让 NapCatQQ 进程保持运行。关闭 NapCatQQ 后，机器人 QQ 就不在线了。

注意事项：

- 建议机器人使用单独 QQ 号，不要直接使用你的主力 QQ。
- 第一次登录可能触发 QQ 设备验证或风控提示，需要按 QQ 客户端提示完成验证。
- `.env` 里的 `SUPERUSERS` 是机器人管理员 QQ 号，不是机器人登录账号。

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

### 7. 配置 NapCatQQ 连接 NoneBot2

在 NapCatQQ 的 WebUI 中登录机器人 QQ 后，添加 OneBot V11 反向 WebSocket 连接：

- 进入：网络配置 / OneBot 网络配置。
- 新建连接。
- 类型：WebSocket 客户端，也就是反向 WebSocket。
- URL：`ws://127.0.0.1:8080/onebot/v11/ws/`
- Access Token：本地调试可以先不填；如果填写，`.env` 中也要设置相同的 `ONEBOT_V11_ACCESS_TOKEN`
- 保存时启用，或者保存后手动启用。

保存并启用后，QQ 中向机器人发送 `/ping`，如果返回 `pong`，说明链路已打通。

### 8. 推荐启动顺序

本地调试时建议按这个顺序来：

1. 启动 NapCatQQ。
2. 在 NapCatQQ WebUI 中确认机器人 QQ 已登录。
3. 启动 NoneBot2：

```bash
source .venv/bin/activate
python main.py
```

4. 在 NapCatQQ WebUI 中启用反向 WebSocket。
5. 用另一个 QQ 给机器人发：

```text
/ping
```

收到 `pong` 即表示成功。

### 9. 常见问题排查

#### 看不到 WebUI 地址

先看 NapCatQQ 启动窗口或日志。WebUI 地址通常会打印为：

```text
http://127.0.0.1:6099/webui?token=xxxxxxxx
```

如果 `6099` 被占用，实际端口可能会变成 `6100` 或更高，必须以日志输出为准。

#### WebUI 打不开

检查：

- NapCatQQ 进程是否还在运行。
- WebUI 地址和端口是否复制完整。
- 本机浏览器访问本机 NapCatQQ 时使用 `127.0.0.1`。
- 远程服务器上的 NapCatQQ 不要直接用本机浏览器访问服务器的 `127.0.0.1`，需要 SSH 隧道，见远程部署部分。

#### 反向 WebSocket 连接失败

检查：

- NoneBot2 是否已经启动。
- NoneBot2 日志里是否显示监听 `127.0.0.1:8080`。
- NapCatQQ 里填写的 URL 是否完全是：

```text
ws://127.0.0.1:8080/onebot/v11/ws/
```

- 如果配置了 Token，NapCatQQ 和 `.env` 中的 Token 必须一致。
- 如果 NapCatQQ 在 Docker 里，而 NoneBot2 在宿主机，`127.0.0.1` 可能指向容器自身，需要改成宿主机可访问地址。

#### QQ 发了 `/ping` 没反应

检查：

- 发送对象是不是机器人 QQ，而不是你自己的 QQ。
- 机器人 QQ 是否仍然在线。
- NapCatQQ 是否收到了消息。
- NoneBot2 控制台是否有收到事件日志。
- 命令前缀是否是 `/`，当前只配置了斜杠命令。

## 远程服务器部署手册

### 1. 服务器基础环境

建议准备：

- Linux 服务器，推荐 Ubuntu 22.04/24.04 或 Debian 12。
- Python 3.10+。
- 可长期运行 NapCatQQ 的环境。
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

#### 2.5 通过 SSH 隧道打开 NapCatQQ WebUI

服务器上的 NapCatQQ WebUI 通常只监听服务器自己的 `127.0.0.1:6099`。本机浏览器不能直接访问服务器的 `127.0.0.1`，需要开 SSH 端口转发：

```bash
ssh -L 6099:127.0.0.1:6099 root@1.2.3.4
```

保持这个 SSH 窗口不要关闭，然后在本机浏览器打开：

```text
http://127.0.0.1:6099/webui
```

如果 NapCatQQ 日志里显示的端口不是 `6099`，例如 `6100`，就把两处端口都改成日志里的实际端口：

```bash
ssh -L 6100:127.0.0.1:6100 root@1.2.3.4
```

如果服务器 SSH 端口不是 `22`，同时加 `-p`：

```bash
ssh -p 2222 -L 6099:127.0.0.1:6099 root@1.2.3.4
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

### 4. 在服务器安装并启动 NapCatQQ

如果服务器是 Ubuntu/Debian，推荐先使用 Linux Shell 方式：

```bash
sudo apt update
sudo apt install -y curl ca-certificates
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
bash napcat.sh --docker n --cli y
```

安装完成后，优先按安装脚本输出的提示启动 NapCatQQ。如果安装了 TUI-CLI，可以尝试：

```bash
sudo napcat
```

在管理界面里启动或管理机器人账号。

如果你选择 Docker 方式，可以使用：

```bash
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
bash napcat.sh --docker y --qq "123456789" --mode ws --proxy 1 --confirm
```

把 `123456789` 换成机器人 QQ 号。

服务器启动 NapCatQQ 后，先确认三件事：

- NapCatQQ 进程没有退出。
- 日志里能看到 WebUI 地址和 token。
- 机器人 QQ 可以在 WebUI 中扫码登录。

### 5. 修改服务端配置

如果 NapCatQQ 和 NoneBot2 在同一台服务器上，可以继续使用：

```env
HOST=127.0.0.1
PORT=8080
```

如果 NapCatQQ 在另一台机器上，需要让 NoneBot2 监听外部地址：

```env
HOST=0.0.0.0
PORT=8080
ONEBOT_V11_ACCESS_TOKEN=请换成强随机字符串
```

同时在服务器安全组或防火墙中只放行必要来源 IP，避免把无 Token 的 OneBot 入口暴露到公网。

### 6. 服务器 NapCatQQ 连接地址

同机部署：

```text
ws://127.0.0.1:8080/onebot/v11/ws/
```

跨机器部署：

```text
ws://服务器IP或域名:8080/onebot/v11/ws/
```

跨机器部署时建议配置 Access Token，并确保 NapCatQQ 和 `.env` 中的 Token 一致。

### 7. 服务器登录机器人 QQ

服务器上同样是 NapCatQQ 负责登录 QQ。常见流程是：

1. 在服务器启动 NapCatQQ。
2. 查看 NapCatQQ 日志中的 WebUI 地址和 token。
3. 如果 WebUI 只监听 `127.0.0.1`，可以用 SSH 端口转发在本机浏览器打开：

```bash
ssh -L 6099:127.0.0.1:6099 user@server
```

然后访问：

```text
http://127.0.0.1:6099/webui
```

4. 在 WebUI 中扫码登录机器人 QQ。
5. 登录完成后，再添加并启用 OneBot V11 反向 WebSocket 连接。

不要把 NapCatQQ WebUI 直接无保护暴露到公网；如果必须远程访问，至少使用防火墙、反向代理认证或 SSH 隧道。

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

### 9. 服务器推荐启动顺序

服务器上建议按这个顺序确认：

1. 启动 NapCatQQ。
2. 通过 SSH 隧道打开 NapCatQQ WebUI。
3. 扫码登录机器人 QQ。
4. 启动或重启 NoneBot2 systemd 服务：

```bash
sudo systemctl restart algoquest
sudo systemctl status algoquest
```

5. 在 NapCatQQ WebUI 中启用 OneBot V11 反向 WebSocket。
6. 用另一个 QQ 发送 `/ping`。
7. 如果没有返回，分别查看 NoneBot2 和 NapCatQQ 日志：

```bash
journalctl -u algoquest -f
```

NapCatQQ 的日志查看方式以你的安装方式为准；Shell/TUI 安装通常可以在管理界面或启动终端里查看，Docker 安装则使用对应容器日志。

## 后续功能开发约定

- 新功能优先放在 `bot/plugins/` 下，按功能拆分插件。
- 随机题和提交评审功能后续建议拆成题库服务、提交解析、沙箱评测、结果回传四部分，避免全部塞进一个插件。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。

## 参考文档

- NoneBot2 文档：https://nonebot.dev/
- NoneBot OneBot 适配器文档：https://onebot.adapters.nonebot.dev/
- NapCatQQ 文档：https://napneko.github.io/
- AtCoder Problems API：https://github.com/kenkoooo/AtCoderProblems/blob/master/doc/api.md
