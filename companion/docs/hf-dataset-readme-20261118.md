# 小可爱 xiaoke.ai · 2026-11-18 完整体验包

统一版本：`20261118114555`。

**核心更新：镜头组合由 2000+ 扩充至 16000+，规模约为此前的 8 倍。** 更丰富的景别、机位、运动与切换节奏，让对话、舞蹈、日常生活和直播拥有更自然的镜头语言与更少的重复感。

## 下载选择

| 使用方式 | 文件 | 位置 | 说明 |
|---|---|---|---|
| 本地完整 A+B | `xiaoke-ai-agent-A-20261118114555.7z` | `20261118114555/` | 程序、前端、Chromium 与 Python 运行时 |
| 本地完整 A+B | `xiaoke-ai-agent-B-20261118114555.7z` | `20261118114555/` | 角色、动作、语音、向量、视觉模型及 PyTorch |
| Online 一体包 | `xiaoke-ai-online-20261118114555.7z` | `online/` | 无需 B，云端对话与向量，默认浏览器识别和 edge-tts |

A、B 必须保持相同时间戳并解压到同一层，运行 A 中的 `xiaoke-ai.exe`。Online 单独解压运行，不要外挂 B。

## 主要功能

- **16000+ 镜头组合**：覆盖更多景别、机位、运动方向与节奏组合，提升角色表演、日常陪伴和舞台呈现的表现力。
- 共同生活、住所、礼物、偏好、回忆、共同旅程、关系阶段、纪念日与回礼。
- Live2D 与 3D 角色舞台、完整动作库、Mixamo 导入和重定向。
- 英雄联盟对局感知、视频陪看、B 站直播互动、塔罗、酒馆、长期记忆和角色卡。
- 本地 Qwen TTS、在线语音、俄语识别与可选 TeraTTSv2。
- 设置页 TTS / ASR 等下拉切换和保存修复；人物自阴影优化。
- 升级保留用户数据，数据库结构变化前自动备份；离线运行时依赖修复。

## 验证与校验

专项测试 124 项通过；A+B 和 Online 启动检查通过；本地 TTS、MiniCPM 运行时检查通过；三包 7z 完整性均为 `Everything is Ok`。

```text
A       6A05E699CFD027E4CB46FC40C56EC9E514642F34FDF0FC43A718B0D88BE1E33E
B       83D30CA54F446B4560FE58633610B571D88C1CA11E0B5254F9EFC4FB02F1CDF6
Online  8AD0B9E96DFFDEAD6C674B35AEC818B236221041E2AA3D4DDCE9580119469757
```

Windows 10+。密钥不随包提供。Online 需要联网并配置自己的模型服务 Key；本地 Qwen TTS 需要兼容的 NVIDIA 显卡和驱动。

---

# xiaoke.ai · November 18, 2026 Release

Unified build version: `20261118114555`.

**Highlight: the camera-combination library has grown from more than 2,000 to over 16,000, roughly eight times its previous size.** Expanded framing, angles, movements and transition pacing bring more natural visual variety to conversations, dances, everyday life and livestreams.

## Choose your edition

| Edition | File | Directory | Contents |
|---|---|---|---|
| Local A+B | `xiaoke-ai-agent-A-20261118114555.7z` | `20261118114555/` | Application, frontend, Chromium and Python runtime |
| Local A+B | `xiaoke-ai-agent-B-20261118114555.7z` | `20261118114555/` | Characters, motions, speech, embeddings, vision models and PyTorch |
| Online all-in-one | `xiaoke-ai-online-20261118114555.7z` | `online/` | Standalone online edition with no B pack; cloud chat and embeddings, with browser recognition and edge-tts by default |

A and B must have exactly the same timestamp. Extract them into the same parent directory and run `xiaoke-ai.exe` from A. Online is extracted and run independently; do not attach a B pack to it.

## Features and improvements

- **Over 16,000 camera combinations:** more shot sizes, camera positions, movement directions and pacing combinations for richer character performances, everyday companionship and stage presentation.
- Shared-life scenes, residences, gifts, preferences and memories, plus shared journeys, relationship stages, anniversaries and return gifts.
- Live2D and 3D character stages, the complete motion collection, and Mixamo import and retargeting.
- League of Legends match awareness, video watch-along, Bilibili live interaction, tarot, Phantom Tavern, long-term memory and character cards.
- Local Qwen TTS, online speech providers, Russian recognition and optional TeraTTSv2.
- Fixed TTS, ASR and other settings dropdowns so selections are written back and saved correctly in the production build.
- Reduced character self-shadow artifacts, safer user-data migration, automatic database rollback backups, and repaired offline runtime dependencies.

## Download and startup notes

Windows 10 or later is required. Chromium and the Python runtime are included, so Chrome and Python do not need to be installed separately. API keys are not supplied with these packages.

- **A+B:** use this edition for local Qwen speech, local embeddings and local vision. A compatible NVIDIA GPU and driver are required for local Qwen TTS. Download both matching files from `20261118114555/`.
- **Online:** use this edition for a smaller standalone internet-connected setup with no B pack and no NVIDIA GPU requirement. Configure your own model-service API key in Settings. Browser Web Speech and edge-tts are the defaults; chat and cloud embeddings require internet access.

## Verification and checksums

All 124 focused tests passed. A+B and Online startup checks passed, including B content discovery and user-data migration. Local TTS and the MiniCPM runtime were verified. Production dropdown selection and saving were tested for TTS and ASR. All three archives passed their 7z integrity checks: `Everything is Ok`.

No billable tests were performed with the user's cloud API keys. Long-duration livestreaming, extended human listening tests and sustained full-GPU stress testing were not included.

```text
A       6A05E699CFD027E4CB46FC40C56EC9E514642F34FDF0FC43A718B0D88BE1E33E
B       83D30CA54F446B4560FE58633610B571D88C1CA11E0B5254F9EFC4FB02F1CDF6
Online  8AD0B9E96DFFDEAD6C674B35AEC818B236221041E2AA3D4DDCE9580119469757
```
