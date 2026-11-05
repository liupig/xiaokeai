# Release History

**English** · [简体中文](./HISTORY.zh-CN.md) · [Back to README](./README.md)

This page records the prebuilt Windows experience packs. Source development continues between packs, so the repository may contain features that are not in the latest download. Newest releases appear first.

## 2026-11-05

**Packages:** `xiaoke-ai-agent-A-20261105173339.7z` + `xiaoke-ai-agent-B-20261105173339.7z`

[GitHub release](https://github.com/liupig/xiaokeai/releases/tag/a-20261105) · [Hugging Face directory](https://huggingface.co/datasets/liupigai/xiaokeai/tree/main/20261105173339)

**Download both packages with timestamp `20261105173339`.** Extract them side by side and run `xiaoke-ai.exe` from A.

- Added Phantom Tavern: four-seat bluffing cards, AI opponents, four art styles, cinematic judgments, and non-blocking voiced play.
- Added Douyin and Bilibili chat, follows, and gifts, plus a local rehearsal lab, fault injection, playback receipts, and gift-response recovery. Real-platform testing is still required.
- Upgraded the local MiniCPM-V eye to continuous video with real timestamps, scene policies, subtitle timelines, game client state, and local OCR.
- Added SillyTavern v1/v2/v3 and AICC card import, v2 PNG export, Lorebooks, alternate greetings, creator metadata, and an optional user persona.
- Added natural-language launching for installed WeGame, Steam, and Epic games with process verification and no automatic installation.
- Added nine MiMo-V2.5-TTS voices, improved speech splitting, unified dsh character sessions, configurable branding, GitHub/Gitee update checks, and completed vision-runtime packaging.

## 2026-10-28

**Packages:** `xiaoke-ai-agent-A-20261028135252.7z` + `xiaoke-ai-agent-B-20261028135252.7z`  
[GitHub release](https://github.com/liupig/xiaokeai/releases/tag/a-20261028)

**Both packages with the matching timestamp are required.** Extract them side by side; the older unversioned `xiaoke-ai-B` cannot run this A package.

- Added movie, short-video, and music companionship. B includes a separate local MiniCPM-V 4.7 1B vision process that shares PyTorch with speech.
- Start watching with the eye button or “watch with me.” Video stays on the local computer, and the companion speaks only when there is something worth saying.
- Improved scene selection so she watches the playing content rather than her own window or the input-method window. The watch log opens from Settings instead of at startup.
- Ordinary chat uses the built-in dsh integration. Added Volcengine drawing and weather, price, and news lookup.
- Fixed the first local Qwen speech warmup hanging and PMX models becoming stuck at 12.5× scale after physics errors or character changes.
- B includes the characters 清宵, kelu, and chun. The desktop pet retains the current character after its window is rebuilt.
- Chat, speech, and the stage remain responsive while the wallet and vision processes are working.
- Increased wishes to 50 per day. When Harness is enabled, Doubao character models require an Ark endpoint ID beginning with `ep-`.

## 2026-10-21

**Package:** `xiaoke-ai-A-20261021090448.7z`  
[GitHub release](https://github.com/liupig/xiaokeai/releases/tag/a-20261021)

- Added local coins and a wishing pool. Idle time, chat, and one wish per day mint coins.
- Wishing drops painted props into the pool and triggers coin rain beside it; the artwork is included in A.
- `xiaoke-ai-B.7z` was repacked on the same date. An older B can still be used if it already works.

## 2026-10-19

**Package:** `xiaoke-ai-A-20261019211256.7z`

- Fixed the desktop-pet package by including the screen helper in A.
- Included locale files beside the executable so spoken tarot works in the pet window.
- Restored local Qwen TTS loading.
- Added clickable QQ-group and Discord invitations to the title bar.
- `xiaoke-ai-B.7z` was repacked on the same date. An older B can still be used if it already works.

## 2026-10-17

**Package:** `xiaoke-ai-A-20261017202306.7z`  
[GitHub release](https://github.com/liupig/xiaokeai/releases/tag/a-20261017)

- The pet remembers its display and position and falls back to a visible workspace when that display is disconnected.
- Tarot controls follow the floating pet.
- Added online speech providers and window reloading.
- Pinned lines and emotional events remain available after leaving the conversation view.
- Continued to use the 2026-10-12 B package; B was not repacked.

## 2026-10-12

**Package:** `xiaoke-ai-A-20261012184939.7z`

- Introduced the transparent, always-on-top desktop pet in Electron.
- Empty space clicks through to the desktop; drag the character to move her and drag a corner to resize.
- `xiaoke-ai-B.7z` was repacked on the same date. An older B can still be used if it already works.

## 2026-10-11

**Package:** `xiaoke-ai-A-20261011203508.7z`

- Separated interface and speech languages: Simplified Chinese, English, Japanese, and Korean.
- English uses Serena, Japanese uses Ono Anna, and Korean uses Sohee by default.
- Settings, tarot, and scenes follow the selected language.
- `xiaoke-ai-B.7z` was repacked on the same date. An older B can still be used if it already works.

## 2026-09-04

**Package:** `xiaoke-ai-A-20260904233641.7z`

- First public Windows A/B experience pack: desktop 3D companionship, voice, lip-sync, motion, dance, camera work, tarot, and memory.
