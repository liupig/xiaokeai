# Companion Studio · AI 陪玩

单机部署的桌面级 Web 产品：挑选或下载 3D 角色，配好人设与声音，用文字或语音聊天。角色用语音、口型、表情、动作和舞蹈实时回应。

本仓库是学习与自用项目，不面向商业分发。内置模型、动作、音乐版权归原作者，请遵守各资产自带的使用条款。

[English](./README.en.md)

## 这个仓库里有什么

| 目录 | 说明 |
|---|---|
| [`companion/`](./companion) | **主产品**：Vue 前端 + FastAPI 后端，完整陪玩工作室 |
| [`companion-3d/`](./companion-3d) | 早期 3D 舞台原型：VRM / GLB / PMX 加载、表情、VMD 舞蹈 |
| [`music-api/`](./music-api) | 独立的学习用音乐检索接口（数据源：爱听音乐网） |

日常使用请跑 `companion/`。`companion-3d` 可以单独打开，用来对照渲染和动作管线。

仓库只提交 **demo 源码** 和情境卡用的背景/舞台贴图。3D 模型、VMD、音乐、语音权重、SQLite、密钥都不入库，克隆后按下面「快速开始」跑起来，再从资产中心导入自己的角色即可。

## 能做什么

- **3D 舞台**：PMX（MMD）、VRM、GLB 热切换；MMD 带 ammo.js 布料物理（头发、裙摆、飘带）。
- **实时动捕**：摄像头直播，或选本地视频反复测。MediaPipe Holistic 在 Worker 里检全身、双手、面部，再驱动当前角色。求解思路参考 [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)。
- **对话表演**：LLM 流式输出里夹 `[emo:]` `[act:]` `[dance:]` `[cam:]` 标签，实时切表情、动作、舞蹈和运镜。没有 API Key 时走本地兜底，表演链路仍可用。
- **语音闭环**：ASR / TTS 可分开选在线或离线。在线：浏览器 Web Speech + edge-tts / 百炼 CosyVoice；离线：SenseVoice-Small + Qwen3-TTS 本地流式。口型跟真实振幅走。
- **长期记忆**：对话里抽出偏好、关系、约定，经 mem0 + 向量库召回后注入下一轮 prompt。
- **情境卡**：内置「今晚这场戏」（雨夜小巷、刚吵完、花树下等），也可按记忆生成当晚情境。
- **证物相册**：舞台截图和短片（mediabunny 编码），按角色归档。
- **资产中心**：本地导入 zip / rar / 单文件（解压、乱码文件名修复、PMX / VMD / 音频自动入库）；可对接[模之屋](https://www.aplaybox.com/)在线搜索下载。
- **角色卡**：模型 + 人设 + 音色 + 情绪到形态键的映射 + 闲置动作。

更细的配置、标签协议和排错见 [`companion/README.md`](./companion/README.md)。

## 技术栈

### 前端（`companion/frontend`）

| 层 | 选用 |
|---|---|
| 框架 | Vue 3、TypeScript、Vite、Pinia、Naive UI |
| 渲染 | [Three.js](https://threejs.org/) 0.185 |
| VRM | [@pixiv/three-vrm](https://github.com/pixiv/three-vrm) |
| MMD | [three-stdlib](https://github.com/pmndrs/three-stdlib) 的 MMDLoader / MMDPhysics + ammo.js |
| 动捕 | [MediaPipe Holistic](https://ai.google.dev/edge/mediapipe/solutions/vision/holistic_landmarker)（Worker） |
| 语音前端 | Web Speech API、[@ricky0123/vad-web](https://github.com/ricky0123/vad)（Silero VAD） |
| 短片 | [mediabunny](https://github.com/Vanilagy/mediabunny) |

引擎代码在 `companion/frontend/src/engine/`（舞台、角色、动作、表情、口型、镜头、闲置）；功能模块在 `features/`（聊天、语音、表演、资产、角色、动捕、记忆、情境、证物）。

### 后端（`companion/backend`）

| 层 | 选用 |
|---|---|
| 服务 | Python 3.11、FastAPI、uvicorn、SQLModel（SQLite） |
| 对话 | OpenAI 兼容 HTTP（可接通义、DeepSeek 等） |
| 记忆 | [mem0](https://github.com/mem0ai/mem0) + 本地 [Qdrant](https://qdrant.tech/)；向量可用云端 embedding 或本机 MiniLM |
| ASR | [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 跑 [SenseVoice-Small](https://github.com/FunAudioLLM/SenseVoice) |
| TTS | [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 本机流式；备选 [edge-tts](https://github.com/rany2/edge-tts)、阿里云百炼 CosyVoice |

## 快速开始

前置：Windows、Node.js 18+、Python 3.11+。有 NVIDIA 显卡时，本地 Qwen3-TTS 会舒服很多。

```bat
cd companion
start.bat
```

首次会装前后端依赖，然后打开 http://localhost:5175 （后端 http://127.0.0.1:8600）。

手动启动：

```bat
:: 后端
cd companion\backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8600 --reload

:: 前端（另开终端）
cd companion\frontend
npm install --legacy-peer-deps
npm run dev
```

设置里填 OpenAI 兼容的 `base_url` / `api_key` / `model` 即可真正聊天。不填也能进舞台：跳舞、表情、动作、口型都还能用。

打开后舞台是空的很正常：把 PMX / VRM / GLB 拖进资产中心即可。离线 ASR / TTS 首次点「准备模型」会下载权重，不要把 `companion/backend/data/` 提交上来。

## 致谢

这个项目站在很多人已经铺好的路上。若有遗漏，欢迎指出。

### 模之屋，以及各位作者

舞台上能看见、能跳、能做表情，首先要感谢 **[模之屋](https://www.aplaybox.com/)**（aplaybox）。

我们用到的 3D 模型、形态键表情、VMD 动作、镜头文件，几乎全部来自模之屋：既是检索和下载的入口，也是 MMD 作者们长期分享作品的地方。没有这个站点，陪玩舞台会是空的。

同时感谢所有在模之屋发布过模型、表情、动作、镜头的作者。你们的作品让角色真正「活」在浏览器里。版权仍归各位作者本人；二次创作请保留借物表，遵守各作品自带的使用规则，禁止二次配布和商业使用。请勿把模之屋 token 提交进仓库。

### 算法与产品思路

- **小冰（Xiaoice）**  
  全双工语音交互的产品与工程思想：一边听一边说、按句排队或打断、沉默后续聊 / 主动搭话 / 告别。我们的对话节奏（`DuplexCmd`、句子类型、ChannelPool 播或不播）直接借鉴了小冰 Jarvis Processor / Transaction 这一侧，而不是把整段回复锁死再播完。
- **[AmyangXYZ](https://github.com/AmyangXYZ) / [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)**（曾用名 MiKaPo）  
  浏览器里把 MediaPipe 关键点解成 MMD 骨骼父空间四元数：静止时 `parent → child` 世界方向当作参考，每帧 shortest-arc，再用 witness 补手臂/大腿扭转。我们的动捕求解器直接借鉴了这条管线，并在 `companion/frontend/src/features/mocap/` 里按 PMX / VRM / GLB 做了适配。没有 MiPo，这条路会绕很远。
- **Géry Casiez, Nicolas Roussel, Daniel Vogel** — [1€ Filter](https://gery.casiez.net/1euro/)（CHI 2012）  
  动捕平滑用的 One-Euro：静止压抖、快动时放宽截止。
- **樋口优 / MikuMikuDance**  
  PMX、VMD、形态键和刚体物理这一整套 MMD 工作流，是舞台能「跳起来」的前提。
- **pixiv / VRoid**  
  VRM 规范让非 MMD 角色也能用同一套表情和骨骼语义。

### 开源引擎与库

- **[mrdoob](https://github.com/mrdoob) / [Three.js](https://github.com/mrdoob/three.js)** — Web 三维渲染。
- **[pixiv](https://github.com/pixiv) / [three-vrm](https://github.com/pixiv/three-vrm)** — VRM 加载、表情、弹簧骨。
- **[Poimandres](https://github.com/pmndrs) / [three-stdlib](https://github.com/pmndrs/three-stdlib)** — 新版 Three 拆出去的 `MMDLoader`、`MMDAnimationHelper`、`MMDPhysics`。
- **[ammo.js](https://github.com/kripken/ammo.js)**（Bullet Physics 的 wasm 端口）— MMD 头发、裙摆、飘带。
- **[Google MediaPipe](https://ai.google.dev/edge/mediapipe)** — Holistic 全身 + 双手 + 面部关键点。
- **[Evan You](https://github.com/yyx990803) / Vue、Vite、Pinia** — 前端骨架。
- **[TuSimple / Naive UI](https://github.com/tusen-ai/naive-ui)** — 设置、资产、角色等面板。
- **[Sebastián Ramírez](https://github.com/tiangolo) / FastAPI、SQLModel** — 后端与 SQLite。
- **[Vanilagy / mediabunny](https://github.com/Vanilagy/mediabunny)** — 证物短片在浏览器里编码。
- **[ricky0123 / vad-web](https://github.com/ricky0123/vad)**、**[Silero VAD](https://github.com/snakers4/silero-vad)**、**[ONNX Runtime](https://onnxruntime.ai/)** — 开麦时在浏览器切语音段。

### 模型、记忆与语音

- **[mem0](https://github.com/mem0ai/mem0)** — 长期记忆的抽取 / 更新 / 召回框架。
- **[Qdrant](https://github.com/qdrant/qdrant)** — 本地向量库。
- **[Hugging Face](https://huggingface.co/)**、**sentence-transformers MiniLM** — 离线 embedding 兜底。
- **[Qwen / 通义](https://github.com/QwenLM)** — Qwen3-TTS 本机流式合成；对话也可走通义兼容接口。
- **[FunAudioLLM / SenseVoice](https://github.com/FunAudioLLM/SenseVoice)** — 离线多语种 ASR。
- **[k2-fsa / sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** — 把 SenseVoice 跑在 CPU 上。
- **[rany2 / edge-tts](https://github.com/rany2/edge-tts)** — 免费在线中文 TTS 备选。
- **阿里云百炼 / CosyVoice** — 云端流式 TTS 备选。
- **[ModelScope](https://www.modelscope.cn/)** — 国内拉 ASR / TTS 权重的镜像。

若你是上述项目或模之屋作品的作者，而我们的说明有误或使用方式不妥，请开 Issue，我们会改文档或代码。

## 说明

- 本仓库代码以学习、研究、个人部署为目的。
- 3D 模型、动作、音乐、音色均有各自版权，不随本仓库转让。
- 模之屋、音乐站等第三方接口可能随时变更或要求登录，不保证长期可用。
- LLM / TTS / ASR 会把对话或语音发到你配置的服务商，请自己看对方的隐私条款。
