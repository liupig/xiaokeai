## 这次，她把娱乐活动安排得明明白白

新版小可爱来了：能陪你追剧，能陪你开局，能接住直播弹幕，还能把 SillyTavern 角色卡请上 3D 舞台。

**一句话：她会玩、会看、会主持，也更会扮演你喜欢的角色了。**

### 下载方式 · Downloads

本版 A/B 时间戳：`20261105173339`

- **GitHub：A 程序包** `xiaoke-ai-agent-A-20261105173339.7z`，已附在本 Release 下方。
- **B 资源包及镜像：** [Hugging Face](https://huggingface.co/datasets/liupigai/xiaokeai/tree/main) · [Google Drive](https://drive.google.com/drive/folders/1mZcD4K90WgO2x2UxteAyMFsQlgTairPl?usp=drive_link) · [百度网盘](https://pan.baidu.com/s/1Y3KuQWG761eP08Uktx36Eg?pwd=xkai)（提取码：`xkai`）

请下载**同一时间戳的 A、B 两包**，用 7-Zip 解压到同一层目录，不要互相嵌套，然后双击 A 目录里的 `xiaoke-ai.exe`。Windows 10+；程序自带 Chromium 和 Python 运行时。聊天及云服务密钥需要自行配置。

A SHA-256：`d96457d83311333172435f101a920bfe34e1ddb3006df74410543b198239cc34`

### 这次更新了什么

- **魅影酒馆**：四人诈牌对局、三名 AI 对手、三膛左轮、计分、四套牌面美术和电影化裁决；边说话边玩，语音不再冻结牌桌。
- **直播互动**：接入抖音和 B 站弹幕、关注与礼物，支持聚合、去重、队列控制和真实播放回执；本地彩排实验室提供虚构观众、故障注入、持久收据与礼物补播。真实平台仍需使用目标直播间自行实测。
- **连续视频陪看**：本地 MiniCPM-V 4.7 1B 理解带真实时间戳的滑动视频窗口；电影、短视频、音乐有独立场景上下文和字幕时间轴，游戏理解可结合英雄联盟客户端状态与本地 OCR。
- **SillyTavern 角色卡生态**：导入 v1/v2/v3 PNG、JSON 和 AICC 卡，导出 v2 PNG 卡；保留多开场白、作者元数据和未知扩展字段，支持世界书与独立用户档案。
- **自然语言开游戏**：打开 WeGame、Steam、Epic 已安装的游戏并检查进程；没有的游戏只打开平台，不擅自安装。
- **更聪明的意图分流**：区分单次查看和持续陪看，也能把“开游戏”和“陪我玩”按正确顺序接起来。
- **语音与会话**：新增小米 MiMo-V2.5-TTS 的 9 个音色与情绪指导，改进断句和短片播放；统一 dsh 角色会话，修复旧回复串轮及本地 Qwen 错误语音问题。
- **桌面与发布体验**：可配置 Logo 和配色，更新检查支持 GitHub 和 Gitee，新增视觉日志开关、窗口控制和社区入口，并补齐视觉运行时与打包整合。

### English

**She can now follow your show, launch your game, host your livestream chat, and watch you bluff across the tavern table.**

- **Phantom Tavern:** four-seat bluffing cards with three AI opponents, scoring, four art styles, cinematic judgments, and voice playback that does not freeze the table.
- **Douyin and Bilibili live interaction:** chat, follows, gifts, aggregation, deduplication, bounded queues, and actual playback receipts. A local rehearsal lab adds scripted viewers, fault injection, persistent receipts, and gift-response recovery. Real-platform testing is still required.
- **Continuous video companionship:** local MiniCPM-V 4.7 1B understands a sliding video window with real timestamps, scene policies, subtitles, and language awareness. Game understanding can use League client state and local OCR.
- **SillyTavern ecosystem:** import v1/v2/v3 PNG/JSON and AICC cards, export v2 PNG cards, preserve alternate greetings and metadata, and use keyword-triggered Lorebooks and an optional user persona.
- **Natural-language game launching:** launch installed WeGame, Steam, and Epic games with process verification; unavailable games are never installed automatically.
- **Voice and desktop:** nine Xiaomi MiMo-V2.5-TTS voices, improved sentence splitting, unified dsh character sessions, configurable branding, GitHub/Gitee update checks, and completed vision-runtime packaging.

Download both matching **A and B (`20261105173339`)** archives, extract them side by side with 7-Zip, and run `xiaoke-ai.exe` from A. The B pack and mirrors are linked above.

## 欢迎加入我们的社区 · Join the Community

无论你是 AI 伴侣玩家、开发者、角色卡作者、MMD/VRM 创作者、直播主播，还是单纯想来看看桌宠今天又在忙什么，都欢迎加入。期待大家一起聊角色、晒舞台、提建议、写代码，也想看看你会把小可爱变成什么样子。

- **QQ 群：** `1124054481`
- **微信：** `xiaokeai3d`
- **Discord：** [加入我们的 Discord](https://discord.gg/xxvXxHP8T)
- **X：** [@iliuPIG](https://x.com/iliuPIG)
- **YouTube：** [@liupig](https://www.youtube.com/@liupig)
- **GitHub：** [liupig/xiaokeai](https://github.com/liupig/xiaokeai)

Everyone is welcome—players, developers, character-card authors, MMD/VRM creators, streamers, and the simply curious. Join us to share ideas, characters, stages, feedback, and code.

| QQ 群二维码 | 微信二维码 |
|---|---|
| <img src="https://github.com/liupig/xiaokeai/releases/download/a-20261105/qq-group.jpg" width="260" alt="QQ group QR code"> | <img src="https://github.com/liupig/xiaokeai/releases/download/a-20261105/wechat-qr.png" width="260" alt="WeChat QR code"> |
