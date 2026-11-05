# Acknowledgements

**English** · [简体中文](./ACKNOWLEDGEMENTS.zh-CN.md) · [Back to README](./README.md)

xiaoke.ai stands on work that many people and communities have already shipped. This page records the projects, authors, ideas, and specifications that made it possible. Inclusion here does not imply endorsement or affiliation. If we have missed someone or described a contribution incorrectly, please open an Issue so we can correct it.

## aplaybox and Every Asset Author

The stage would be empty without **[模之屋 / aplaybox](https://www.aplaybox.com/)**.

Almost every 3D model, facial morph, VMD motion, and camera file used during development comes from aplaybox: it is both a search/download gateway and a place where MMD authors have shared their work for years.

We thank every author who has published models, expressions, motions, or cameras there. Their work is what allows characters to come alive on the stage. Copyright remains with each original author. Keep credit lists, follow each work's own terms, and do not redistribute assets or use them commercially without permission. Never commit an aplaybox token to this repository.

## SillyTavern and the Character-Card Community

Character-card compatibility builds on the open ecosystem established by **[SillyTavern](https://github.com/SillyTavern/SillyTavern)** and the community **[Character Card V2 specification](https://github.com/malfoyslastname/character-card-spec-v2)**.

xiaoke.ai imports SillyTavern v1/v2/v3 and AICC cards, exports v2 cards, preserves alternate greetings and creator metadata, and adapts keyword-triggered Lorebooks to its own layered prompt stack and 3D stage. The card formats and Lorebook concept are not original to this project. Character cards remain copyrighted by their respective authors, and compatibility does not imply affiliation with SillyTavern.

## Product Ideas and Algorithms

- **Xiaoice (小冰)**  
  Full-duplex spoken interaction: listen while speaking, queue or barge in per sentence, then continue, proactively talk, or say goodbye after silence. Our dialogue timing—`DuplexCmd`, sentence types, and play-or-skip decisions in the pool—follows that side of Xiaoice instead of locking an entire reply before playback.
- **Doubao (豆包)**  
  Multi-part system prompts restacked each turn, account-level persona versus session role-play, memory guardrails, and code-side interception before prompt text. Our `prompt_stack` is inferred from public behavior; see [`companion/docs/persona-stack.md`](./companion/docs/persona-stack.md).
- **[AmyangXYZ](https://github.com/AmyangXYZ) / [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)** (formerly MiKaPo)  
  MediaPipe landmarks to MMD parent-local quaternions: rest `parent → child` world direction as the reference, shortest arc per frame, and witness bones for arm/thigh roll. Our solver in `companion/frontend/src/features/mocap/` follows that pipeline and adapts it for PMX, VRM, and GLB.
- **Géry Casiez, Nicolas Roussel, Daniel Vogel** — [1€ Filter](https://gery.casiez.net/1euro/) (CHI 2012)  
  One-Euro smoothing for motion capture: damp jitter at rest and open the cutoff during fast movement.
- **Higuchi Yu / MikuMikuDance**  
  PMX, VMD, morphs, and rigid-body physics—the workflow on which the stage dances.
- **pixiv / VRoid**  
  The VRM specification lets non-MMD characters share expression and bone semantics.
- **Rider–Waite tarot tradition**  
  Names, numbers, and symbols follow the tradition; composition and color are original. We do not trace the Waite–Smith plates.

## Engines and Libraries

- **[mrdoob](https://github.com/mrdoob) / [Three.js](https://github.com/mrdoob/three.js)** — Web 3D rendering.
- **[pixiv](https://github.com/pixiv) / [three-vrm](https://github.com/pixiv/three-vrm)** — VRM loading, expressions, and spring bones.
- **[Poimandres](https://github.com/pmndrs) / [three-stdlib](https://github.com/pmndrs/three-stdlib)** — `MMDLoader`, `MMDAnimationHelper`, and `MMDPhysics` split from newer Three.js.
- **[ammo.js](https://github.com/kripken/ammo.js)** — Bullet Physics WebAssembly for MMD hair, skirts, and ribbons.
- **[Google MediaPipe](https://ai.google.dev/edge/mediapipe)** — Holistic body, hand, and face landmarks.
- **[Evan You](https://github.com/yyx990803) / Vue, Vite, Pinia** — frontend foundation.
- **[TuSimple / Naive UI](https://github.com/tusen-ai/naive-ui)** — settings, assets, and character panels.
- **[Sebastián Ramírez](https://github.com/tiangolo) / FastAPI, SQLModel** — backend and SQLite.
- **[Electron](https://www.electronjs.org/)** and **[PyInstaller](https://pyinstaller.org/)** — desktop window and single-file launcher.
- **[Vanilagy / mediabunny](https://github.com/Vanilagy/mediabunny)** — keepsake clips encoded in the browser.
- **[ricky0123 / vad-web](https://github.com/ricky0123/vad)**, **[Silero VAD](https://github.com/snakers4/silero-vad)**, and **[ONNX Runtime](https://onnxruntime.ai/)** — browser speech segmentation.
- **WebRTC AEC3** — cancels the companion's own voice while the microphone is open.

## Models, Memory, and Speech

- **[mem0](https://github.com/mem0ai/mem0)** — extraction, updating, and recall for long-term memory.
- **[Qdrant](https://github.com/qdrant/qdrant)** — local vector store.
- **[Hugging Face](https://huggingface.co/)** and **sentence-transformers MiniLM** — offline embedding fallback and model distribution.
- **[Qwen / 通义](https://github.com/QwenLM)** — Qwen3-TTS local streaming; chat can use Qwen-compatible APIs.
- **[FunAudioLLM / SenseVoice](https://github.com/FunAudioLLM/SenseVoice)** — offline multilingual ASR.
- **[k2-fsa / sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** — SenseVoice on CPU.
- **[rany2 / edge-tts](https://github.com/rany2/edge-tts)** — online Microsoft neural-speech fallback.
- **Alibaba DashScope / CosyVoice** — cloud streaming TTS.
- **[ModelScope](https://www.modelscope.cn/)** — mainland mirror for ASR/TTS weights.
- **ModelBest / MiniCPM-V and MiniCPM-o** — local visual companionship and multimodal experiments.
- **Xiaomi MiMo** — MiMo chat models and MiMo-V2.5-TTS voices.
- **DeepSeek Harness (`deepseek-harness-sdk`)** — the agent runtime used by the unified character conversation path.

## Live-Interaction Research and References

The livestream design also learned from published work and existing implementations:

- **[AI-Vtuber](https://github.com/Ikaros-521/AI-Vtuber)** — staged message processing, response throttling, and audio-queue behavior.
- **[Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)** — platform adapter boundaries and session handling.
- **[Streamer.bot Actions](https://docs.streamer.bot/guide/core/actions)** — serialized action queues and the distinction between generation and playback.
- **[Twitch EventSub](https://dev.twitch.tv/docs/eventsub/)** — heartbeat, reconnect, revocation, and event-delivery semantics used as reliability references; xiaoke.ai does not claim a Twitch integration.
- **[Neuro-sama audience research](https://arxiv.org/abs/2509.10427)** — the value of sustained persona and shared audience participation. The research does not disclose Neuro-sama's internal implementation, and we do not claim to reproduce it.

## Asset and License Reminder

Source code and project-generated tarot/scene art are licensed under [Apache License 2.0](./LICENSE). The xiaoke.ai / 小可爱 names and marks are not transferred. Third-party models, motions, cameras, music, voices, character cards, and other assets remain under their authors' own terms. See [NOTICE](./NOTICE) before redistribution or commercial use.

If you are an author of any project or asset listed above and something here is wrong or used inappropriately, please open an Issue. We will correct the documentation or the code.
