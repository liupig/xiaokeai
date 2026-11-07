# 致谢

[English](./ACKNOWLEDGEMENTS.md) · **简体中文** · [返回 README](./README.zh-CN.md)

xiaoke.ai 站在许多人、许多社区已经铺好的路上。这一页记录让项目得以实现的作品、作者、产品思路与技术规范。列入本文不代表对方为本项目背书，也不代表双方存在隶属关系。如果有遗漏或描述不准确，欢迎提交 Issue，我们会核实并修正。

## 模之屋，以及各位资产作者

舞台上能看见、能跳、能做表情，首先要感谢 **[模之屋 / aplaybox](https://www.aplaybox.com/)**。

开发过程中使用的 3D 模型、形态键表情、VMD 动作和镜头文件，几乎全部来自模之屋：它既是检索与下载入口，也是 MMD 作者们长期分享作品的地方。

同时感谢所有在模之屋发布过模型、表情、动作或镜头的作者。正是这些作品，让角色真正「活」在舞台上。版权仍归各位原作者；二次创作请保留借物表，遵守各作品自带的使用规则，未经许可不要二次配布或商用。请勿把模之屋 token 提交进仓库。

## SillyTavern 与角色卡社区

角色卡兼容基于 **[SillyTavern（酒馆）](https://github.com/SillyTavern/SillyTavern)** 建立的开放生态和社区 **[Character Card V2 规范](https://github.com/malfoyslastname/character-card-spec-v2)**。

xiaoke.ai 支持导入 SillyTavern v1/v2/v3 和 AICC 角色卡、导出 v2 卡、保留多开场白与作者元数据，并将关键词触发的世界书接入自己的分层提示词和 3D 舞台。角色卡格式与世界书概念并非本项目原创。角色卡版权归原作者，兼容支持也不代表与 SillyTavern 官方存在隶属关系。

## 产品思路与算法

- **小冰（Xiaoice）**  
  全双工语音交互的产品与工程思想：一边听一边说、按句排队或打断、沉默后续聊／主动搭话／告别。我们的对话节奏——`DuplexCmd`、句子类型、Pool 播或不播——借鉴了小冰这一侧，而不是把整段回复锁死再播完。
- **豆包（Doubao）**  
  多段 system 每轮动态拼接、账号级人设与会话级扮演分层、记忆护栏、代码侧拦截优先于 prompt 文本。我们的 `prompt_stack` 按公开行为反推了这套组织方式，详见 [`companion/docs/persona-stack.md`](./companion/docs/persona-stack.md)。
- **[AmyangXYZ](https://github.com/AmyangXYZ) / [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)**（曾用名 MiKaPo）  
  浏览器里把 MediaPipe 关键点解成 MMD 骨骼父空间四元数：静止时以 `parent → child` 世界方向作为参考，每帧 shortest-arc，再用 witness 补手臂和大腿扭转。我们的动捕求解器位于 `companion/frontend/src/features/mocap/`，遵循这条管线并适配 PMX、VRM、GLB。
- **Géry Casiez、Nicolas Roussel、Daniel Vogel** — [1€ Filter](https://gery.casiez.net/1euro/)（CHI 2012）  
  动捕平滑使用 One-Euro：静止压抖，快速运动时放宽截止。
- **樋口优 / MikuMikuDance**  
  PMX、VMD、形态键和刚体物理这一整套 MMD 工作流，是舞台能「跳起来」的前提。
- **pixiv / VRoid**  
  VRM 规范让非 MMD 角色也能共用表情和骨骼语义。
- **韦特塔罗传统**  
  牌名、编号与符号沿用传统体系；牌面构图和上色全部原创重绘，不描韦特彩图。

## 开源引擎与库

- **[mrdoob](https://github.com/mrdoob) / [Three.js](https://github.com/mrdoob/three.js)** — Web 三维渲染。
- **[pixiv](https://github.com/pixiv) / [three-vrm](https://github.com/pixiv/three-vrm)** — VRM 加载、表情、弹簧骨。
- **[Poimandres](https://github.com/pmndrs) / [three-stdlib](https://github.com/pmndrs/three-stdlib)** — 从新版 Three.js 拆出的 `MMDLoader`、`MMDAnimationHelper`、`MMDPhysics`。
- **[ammo.js](https://github.com/kripken/ammo.js)** — Bullet Physics 的 WebAssembly 端口，用于 MMD 头发、裙摆和飘带。
- **[Google MediaPipe](https://ai.google.dev/edge/mediapipe)** — Holistic 全身、双手和面部关键点。
- **[Untitled Story](https://github.com/Untitled-Story/untitled-pixi-live2d-engine) / untitled-pixi-live2d-engine、PixiJS** — 独立 Live2D 渲染与 Cubism 模型加载。
- **[Live2D](https://www.live2d.com/) / Cubism Core for Web** — Live2D 模型运行时；遵循 Live2D Proprietary Software License，文件保留原始许可声明。
- **[Evan You](https://github.com/yyx990803) / Vue、Vite、Pinia** — 前端基础框架。
- **[TuSimple / Naive UI](https://github.com/tusen-ai/naive-ui)** — 设置、资产和角色面板。
- **[Sebastián Ramírez](https://github.com/tiangolo) / FastAPI、SQLModel** — 后端与 SQLite。
- **[Electron](https://www.electronjs.org/)**、**[PyInstaller](https://pyinstaller.org/)** — 桌面窗口壳与单文件启动器。
- **[Vanilagy / mediabunny](https://github.com/Vanilagy/mediabunny)** — 证物短片在浏览器里编码。
- **[ricky0123 / vad-web](https://github.com/ricky0123/vad)**、**[Silero VAD](https://github.com/snakers4/silero-vad)**、**[ONNX Runtime](https://onnxruntime.ai/)** — 浏览器语音切分。
- **WebRTC AEC3** — 开麦时抵消角色自己的声音。

## 模型、记忆与语音

- **[mem0](https://github.com/mem0ai/mem0)** — 长期记忆的抽取、更新与召回框架。
- **[Qdrant](https://github.com/qdrant/qdrant)** — 本地向量库。
- **[Hugging Face](https://huggingface.co/)**、**sentence-transformers MiniLM** — 离线向量兜底与模型分发。
- **[Qwen / 通义](https://github.com/QwenLM)** — Qwen3-TTS 本机流式合成；对话也可使用通义兼容接口。
- **[FunAudioLLM / SenseVoice](https://github.com/FunAudioLLM/SenseVoice)** — 离线多语种 ASR。
- **[k2-fsa / sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** — 让 SenseVoice 跑在 CPU 上。
- **[rany2 / edge-tts](https://github.com/rany2/edge-tts)** — 在线微软神经网络语音备选。
- **阿里云百炼 / CosyVoice** — 云端流式 TTS。
- **[ModelScope](https://www.modelscope.cn/)** — 国内下载 ASR/TTS 权重的镜像。
- **面壁智能 / MiniCPM-V、MiniCPM-o** — 本地视觉陪看与多模态实验。
- **小米 MiMo** — MiMo 对话模型与 MiMo-V2.5-TTS 音色。
- **DeepSeek Harness（`deepseek-harness-sdk`）** — 统一角色会话所使用的代理运行时。

## 直播互动的调研与参考

直播功能的设计也参考了公开论文和已有实现：

- **[AI-Vtuber](https://github.com/Ikaros-521/AI-Vtuber)** — 分阶段消息处理、答谢节流和音频队列行为。
- **[Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)** — 平台适配边界和会话处理。
- **[Streamer.bot Actions](https://docs.streamer.bot/guide/core/actions)** — 串行动作队列，以及生成完成与播放完成的区别。
- **[Twitch EventSub](https://dev.twitch.tv/docs/eventsub/)** — 心跳、重连、订阅撤销和事件投递语义，作为可靠性参考；本项目并未因此宣称已接入 Twitch。
- **[Neuro-sama 观众研究](https://arxiv.org/abs/2509.10427)** — 持续人设与观众共同参与的价值。该研究没有公开 Neuro-sama 的内部实现，我们也不声称复刻了其算法。

## 资产与协议提醒

源码和项目原创塔罗／情境美术采用 [Apache License 2.0](./LICENSE)。xiaoke.ai / 小可爱名称与标识不随代码转让；第三方模型、动作、镜头、音乐、音色、角色卡和其他资产遵循各自作者的条款。再分发或商用前请阅读 [NOTICE](./NOTICE)。

如果你是上述项目或素材的作者，而这里的说明有误或使用方式不妥，请提交 Issue。我们会修正文档或代码。
