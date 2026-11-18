# 2026-11-18 · 小可爱 A + Online 完整体验包

统一版本：**`20261118114555`**。这次 A 程序包和 Online 在线一体包放在同一个 Release，按需选择即可；本地完整能力请同时下载同版本 B 资源包。

**本次重点：镜头组合从 2000+ 扩充至 16000+，规模约为此前的 8 倍。** 更丰富的景别、机位、运动与切换组合，让角色表演、日常陪伴和舞台呈现不再只有少量重复镜头。

## 下载与启动

### 本地 A+B：语音、向量与视觉可跑在本机

1. 下载本 Release 的 `xiaoke-ai-agent-A-20261118114555.7z`。
2. 到 [Hugging Face 的 20261118114555 目录](https://huggingface.co/datasets/liupigai/xiaokeai/tree/main/20261118114555) 下载同版本 `xiaoke-ai-agent-B-20261118114555.7z`。
3. 用 7-Zip 将 A、B 解压到**同一层目录**，不要嵌套，运行 A 中的 `xiaoke-ai.exe`。
4. A 会自动识别同时间戳的 B；本地 Qwen TTS 需要兼容的 NVIDIA 显卡及驱动。

### Online：一个包联网使用

1. 下载本 Release 的 `xiaoke-ai-online-20261118114555.7z`，也可从 [Hugging Face Online 目录](https://huggingface.co/datasets/liupigai/xiaokeai/tree/main/online) 下载。
2. 解压后直接运行 `xiaoke-ai.exe`，**不需要 A、B，也不需要 NVIDIA 显卡**。
3. 在「设置 → AI 对话」配置自己的火山方舟 Key。默认浏览器 Web Speech 识别、edge-tts 合成；对话和云端向量需要联网。

Windows 10+；包内已带 Chromium 和 Python 运行时，目标电脑不需要另装 Chrome 或 Python。密钥不随包发布。

## 这次更新了什么

### 陪伴与玩法

- **16000+ 镜头组合**：从此前 2000+ 大幅扩充，覆盖更多景别、机位、运动方向与节奏组合；对话、舞蹈、生活场景和直播可以选择更合适的镜头语言，减少重复感，增强陪伴的临场感和舞台表现力。
- **共同生活与旅程**：生活场景、住所、礼物、偏好、共同回忆、好感与关系阶段、纪念日、回礼和角色自主偏好，打通金币、道具与存档闭环。
- **Live2D 舞台**：模型导入、热键、贴图处理、动作与交互；完善生命周期和资源管理。
- **3D 与动作**：完整动作资源、Mixamo 导入与重定向、动作预览；优化舞台渲染和人物边缘行为。
- **英雄联盟陪伴**：增强对局、事件与队伍状态感知，改进战局解说与视觉服务恢复。
- **陪看与直播**：更自然的陪看生成，修复重复生成与重复播放；新增 B 站登录、WBI 请求、弹幕解析、互动主持和交付审计。

### 语音与稳定性

- 本地 Qwen3-TTS、浏览器识别、edge-tts、豆包、小米等引擎可按需选择；增加俄语识别和可选 TeraTTSv2。
- **修复设置页切换失效**：生产版下拉框可正常切换 TTS、ASR 与其他选项，保存后不会跳回旧值。
- **修复人物阴影**：减少脸部、睫毛和头发上的三角形自阴影，同时保留人物向地面和舞台投影。
- **升级保留用户数据**：迁移到统一用户数据目录，数据库结构变更前自动保留回滚副本。
- **修复离线运行时依赖**：清理混合版本残留，补齐 TTS / Transformers 依赖，约束 NumPy 与 Numba 的兼容版本。

## 已完成验证

- 最新源码专项测试：**124 项全部通过**。
- A+B 实际启动、B 资源关联、用户数据迁移、本地 TTS 与 MiniCPM 运行时检查通过。
- Online 依赖、后端导入与实际启动检查通过。
- 生产版 TTS、ASR 下拉切换及保存测试通过。
- 三个 7z 均通过完整性检查：**Everything is Ok**。

未使用用户云端 Key 做计费模型测试；未做长时间直播推流、人工音频试听或显卡满载压力测试。

## SHA-256

```text
A       6A05E699CFD027E4CB46FC40C56EC9E514642F34FDF0FC43A718B0D88BE1E33E
B       83D30CA54F446B4560FE58633610B571D88C1CA11E0B5254F9EFC4FB02F1CDF6
Online  8AD0B9E96DFFDEAD6C674B35AEC818B236221041E2AA3D4DDCE9580119469757
```

## English · Full Release Notes

Unified build version: **`20261118114555`**. The A application pack and the Online all-in-one pack are published together in this Release. Choose the edition that matches your setup. For the complete local experience, download the B content pack with the same version timestamp as A.

**Highlight of this release: the camera-combination library has grown from more than 2,000 to over 16,000 combinations, roughly eight times its previous size.** A much broader range of framing, angles, movements and transitions gives character performances, everyday companionship and stage presentations far more visual variety.

### Download and start

#### A+B: local speech, embeddings and vision

1. Download `xiaoke-ai-agent-A-20261118114555.7z` from this Release.
2. Download `xiaoke-ai-agent-B-20261118114555.7z` from the [Hugging Face 20261118114555 directory](https://huggingface.co/datasets/liupigai/xiaokeai/tree/main/20261118114555). The version timestamp must match A exactly.
3. Extract both archives with 7-Zip **into the same parent directory**, without nesting one inside the other. Run `xiaoke-ai.exe` from the A directory.
4. A automatically detects the matching B pack. Local Qwen TTS requires a compatible NVIDIA GPU and driver.

#### Online: a standalone internet-connected edition

1. Download `xiaoke-ai-online-20261118114555.7z` from this Release, or from the [Hugging Face Online directory](https://huggingface.co/datasets/liupigai/xiaokeai/tree/main/online).
2. Extract the archive and run `xiaoke-ai.exe`. **A and B are not required, and neither is an NVIDIA GPU.**
3. Open **Settings → AI Chat** and enter your own Volcengine Ark API key. Browser Web Speech is used for recognition by default and edge-tts for synthesis. Chat and cloud embeddings require an internet connection.

Windows 10 or later is required. Chromium and the Python runtime are included, so there is no need to install Chrome or Python separately. API keys are never bundled with the release.

### What is new

#### Companion experiences and activities

- **Over 16,000 camera combinations:** expanded from the previous 2,000+, with a much wider range of shot sizes, camera positions, movement directions and pacing combinations. Conversations, dances, daily-life scenes and livestreams can use more suitable cinematic language, reducing repetition and creating a stronger sense of presence and a richer stage experience.
- **Shared life and journeys:** everyday scenes, residences, gifts, preferences, shared memories, affection and relationship stages, anniversaries, return gifts and autonomous character preferences, connected through a persistent inventory, coins and save-data loop.
- **Live2D stage:** model import, hotkeys, texture processing, motions and interactions, with improved lifecycle and asset management.
- **3D and motions:** the complete motion collection, Mixamo import and retargeting, and motion previews, together with improved stage rendering and character behavior near screen edges.
- **League of Legends companionship:** better awareness of match, event and team states, improved in-game commentary, and more reliable vision-service recovery.
- **Watch-along and livestreaming:** more natural watch-along generation, fixes for duplicate generation and playback, and new Bilibili login, WBI requests, chat-packet parsing, interactive hosting and delivery auditing.

#### Speech and reliability

- Choose between local Qwen3-TTS, browser recognition, edge-tts, Doubao, Xiaomi and other supported engines. Russian recognition and optional TeraTTSv2 support are also included.
- **Settings dropdowns fixed:** TTS, ASR and other settings can now be changed in the production build and saved without immediately reverting to their previous values.
- **Improved character shadows:** reduced triangular self-shadow artifacts on faces, eyelashes and hair while retaining shadows cast onto the ground and stage.
- **User data preserved across upgrades:** settings and personal data are migrated to a unified user-data directory, with an automatic rollback backup before a database schema change.
- **Offline runtime dependencies repaired:** stale mixed-version files are removed, missing TTS / Transformers dependencies are included, and NumPy is constrained to a Numba-compatible range.

### Verification completed

- **124 focused source tests passed.**
- A+B startup, B content discovery, user-data migration, local TTS and the MiniCPM runtime were verified.
- Online dependency checks, backend imports and application startup were verified.
- TTS and ASR dropdown selection and saving were tested against the production frontend.
- All three 7z archives passed their integrity checks: **Everything is Ok**.

No billable tests were performed with the user's cloud API keys. Long-duration livestreaming, extended human listening tests and sustained full-GPU stress testing were not part of this verification.

### SHA-256

```text
A       6A05E699CFD027E4CB46FC40C56EC9E514642F34FDF0FC43A718B0D88BE1E33E
B       83D30CA54F446B4560FE58633610B571D88C1CA11E0B5254F9EFC4FB02F1CDF6
Online  8AD0B9E96DFFDEAD6C674B35AEC818B236221041E2AA3D4DDCE9580119469757
```

## 社区 · Community

- QQ 群 · QQ group：`1124054481`
- 微信 · WeChat：`xiaokeai3d`
- Discord：https://discord.gg/xxvXxHP8T
- X：https://x.com/iliuPIG
- YouTube：https://www.youtube.com/@liupig
