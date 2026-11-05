github： https://github.com/liupig/xiaokeai

百度云盘：https://pan.baidu.com/s/1Y3KuQWG761eP08Uktx36Eg?pwd=xkai

huggingface： https://huggingface.co/datasets/liupigai/xiaokeai/tree/main

google drive： https://drive.google.com/drive/folders/1mZcD4K90WgO2x2UxteAyMFsQlgTairPl?usp=drive_link

演示视频：
https://www.bilibili.com/video/BV1ABWc6zEo3

xiaoke.ai 小可爱 is an open-source 3D AI companion: a local desktop 3D virtual companion. A VRM, MMD (PMX), or GLB character sits across from you: voice chat, lip-sync, expression, motion, dance, and camera, with tarot and long-term memory kept on the machine. She can also stay for a movie, a short video, or a song. A local eye watches the screen and hears the sound; the picture never leaves this computer, and she speaks only when there is something worth saying. In the desktop app she can leave the stage and float as a transparent desktop pet. Interface language and speech language are separate: Simplified Chinese, English, Japanese, and Korean.

Also called: open-source 3D AI companion, 3D AI companion, AI companion, local AI companion, transparent desktop pet, waifu, awesome-ai, watch a movie together, AI movie companion, 开源 3D AI 伴侣, AI 伴侣, 本地 AI 伴侣, 开源 3D 陪玩, 虚拟陪玩, 本地桌宠, 透明桌宠, VRM chatbot, MMD desktop pet, AI VTuber, 陪看电影, 陪刷视频, 陪听音乐, 视觉互动.

xiaoke.ai（小可爱） 是开源 3D AI 伴侣，也是本地 3D 陪玩 / 虚拟陪玩。VRM、MMD（PMX）、GLB 角色坐在对面：语音聊天、口型、表情、动作、舞蹈、运镜，对面抽塔罗，长期记忆留在本机。也可以陪你看电影、刷视频、听音乐。本机的眼睛看着屏幕、听着声音，画面不离开这台电脑，有一句值得说她才开口。桌面程序里还可以离开舞台，变成透明桌宠浮在桌面上。界面语言和对话语言分开，支持简体中文、英语、日语、韩语。

别人会用这些词来找：开源 3D AI 伴侣、AI 伴侣、本地 AI 伴侣、3D AI companion、open-source AI companion、AI companion、waifu、awesome-ai、开源 3D 陪玩、虚拟陪玩、本地桌宠、透明桌宠、VRM 聊天、MMD 陪玩、AI VTuber、虚拟主播、陪看电影、陪刷视频、陪听音乐、视觉互动。

---

## 2026-11-05 · A/B 程序包

新版文件按 14 位时间戳目录整理，时间戳可直接用于版本排序：

[`20261105173339/`](https://huggingface.co/datasets/liupigai/xiaokeai/tree/main/20261105173339)

| 包 | 下载 | 大小 | SHA-256 |
|---|---|---:|---|
| A 程序包 | [`xiaoke-ai-agent-A-20261105173339.7z`](https://huggingface.co/datasets/liupigai/xiaokeai/resolve/main/20261105173339/xiaoke-ai-agent-A-20261105173339.7z) | 644,203,792 字节 | `d96457d83311333172435f101a920bfe34e1ddb3006df74410543b198239cc34` |
| B 资源包 | [`xiaoke-ai-agent-B-20261105173339.7z`](https://huggingface.co/datasets/liupigai/xiaokeai/resolve/main/20261105173339/xiaoke-ai-agent-B-20261105173339.7z) | 11,870,433,317 字节 | `d592bed0a4e65ccecdb62fc339a3e7f293fe60300a08e5c1c1eb9a3428c8c0bc` |

请下载同一时间戳的 A、B 两包，用 7-Zip 解压到同一层目录，然后双击 A 目录中的 `xiaoke-ai.exe`。Windows 10+，自带 Chromium 和 Python 运行时。聊天与云服务密钥需自行配置。

### 本次更新

- **魅影酒馆：** 四人诈牌对局、三名 AI 对手、四套牌面、电影化裁决，语音播放不冻结牌桌。
- **直播互动：** 抖音和 B 站弹幕、关注与礼物，支持聚合、去重、队列控制、真实播放回执、本地彩排和礼物补播。真实平台仍需使用目标直播间自行实测。
- **连续视频陪看：** 本地 MiniCPM-V 4.7 1B 理解带真实时间戳的滑动视频窗口，支持场景策略、字幕时间轴、游戏客户端状态与本地 OCR。
- **SillyTavern 角色卡：** 导入 v1/v2/v3 PNG、JSON 和 AICC 卡，导出 v2 PNG 卡，支持世界书、多个开场白、作者元数据和用户档案。
- **自然语言开游戏：** 打开 WeGame、Steam、Epic 已安装游戏并检查进程，不自动安装缺失游戏。
- **语音与桌面：** 新增 MiMo-V2.5-TTS 9 个音色，改进断句、统一 dsh 角色会话，支持品牌主题、GitHub/Gitee 更新检查，并补齐视觉运行时与打包整合。

完整发布说明：[GitHub Release](https://github.com/liupig/xiaokeai/releases/tag/a-20261105)

### English

The `20261105173339/` directory contains the matching A application and B content packs. Download both, extract them side by side with 7-Zip, and run `xiaoke-ai.exe` from A on Windows 10+.

- **Phantom Tavern:** four-seat bluffing cards with AI opponents, four art styles, cinematic judgments, and non-blocking voiced play.
- **Live interaction:** Douyin and Bilibili chat, follows, and gifts, with aggregation, deduplication, bounded queues, playback receipts, a local rehearsal lab, and gift-response recovery. Real-platform testing is still required.
- **Continuous video companionship:** local MiniCPM-V 4.7 1B understands timestamped sliding video with scene policies, subtitles, game client state, and local OCR.
- **SillyTavern ecosystem:** import v1/v2/v3 PNG/JSON and AICC cards, export v2 PNG cards, and use Lorebooks and an optional user persona.
- **Natural-language game launching:** launch installed WeGame, Steam, and Epic games with process verification; unavailable games are never installed automatically.
- **Voice and desktop:** nine MiMo-V2.5-TTS voices, improved sentence splitting, unified dsh sessions, configurable branding, GitHub/Gitee update checks, and completed vision-runtime packaging.

Full release notes: [GitHub Release](https://github.com/liupig/xiaokeai/releases/tag/a-20261105)

---

## 欢迎加入我们的社区 · Join the Community

无论你是 AI 伴侣玩家、开发者、角色卡作者、MMD/VRM 创作者、主播，还是单纯想来看看，都欢迎加入。期待大家一起聊角色、晒舞台、提建议、写代码。

Everyone is welcome—players, developers, character-card authors, MMD/VRM creators, streamers, and the simply curious. Share characters, stages, ideas, feedback, and code with us.

- **QQ 群：** `1124054481`
- **微信：** `xiaokeai3d`
- **Discord：** [加入我们的 Discord](https://discord.gg/xxvXxHP8T)
- **X：** [@iliuPIG](https://x.com/iliuPIG)
- **YouTube：** [@liupig](https://www.youtube.com/@liupig)
- **GitHub：** [liupig/xiaokeai](https://github.com/liupig/xiaokeai)

QQ 群和微信二维码也附在 [GitHub Release](https://github.com/liupig/xiaokeai/releases/tag/a-20261105) 正文及附件中。
