# xiaoke.ai · 小可爱

> **开源免费 · 本地运行 —— 让一个会说、会动、会记得你的她，坐到你对面。**

单机部署的桌面级 3D 陪伴产品：挑选或下载 3D 角色，配好人设与声音，用文字或语音聊天。角色用语音、口型、表情、动作、舞蹈和运镜实时回应；还能坐在你对面给你抽一副牌。

- **开源**：前后端源码全部公开，怎么跑、怎么改都写在文档里。
- **免费**：没有付费墙、会员、次数卡。LLM / 语音可以全走本地或免费服务，一分钱不花也能完整体验。
- **本地**：对话、记忆、证物、语音权重都在你自己的电脑上；只有你配置的 LLM / 云语音服务商会收到请求。
- **非商用**：源码按 [PolyForm Noncommercial 1.0.0](./LICENSE) 授权，个人、学习、研究、非营利组织随便用、随便改、随便转发，不得用于商业目的。

舞台上的 3D 模型、动作、音乐、音色不在本协议内，版权归原作者，请遵守各资产自带的使用条款（多数同样禁止商用和二次配布）。

[English](./README.en.md) · [xiaoke.ai](https://xiaoke.ai)

## 看一眼

<table>
  <tr>
    <td width="50%"><img src="./companion/docs/screenshots/stage-chat.jpg" alt="舞台与对话" /></td>
    <td width="50%"><img src="./companion/docs/screenshots/stage-hud.jpg" alt="当前表演 HUD：景别、运镜、站位、动作" /></td>
  </tr>
  <tr>
    <td align="center">对话即表演：说话时表情、动作、运镜跟着走</td>
    <td align="center">右上角实时显示这一句用的景别 × 运镜 × 站位 × 动作，不好可以当场「去掉」</td>
  </tr>
  <tr>
    <td><img src="./companion/docs/screenshots/tarot-fan.jpg" alt="塔罗：牌背升起围成扇面" /></td>
    <td><img src="./companion/docs/screenshots/tarot-spread.jpg" alt="塔罗：三张牌落入过去 / 现在 / 未来牌位" /></td>
  </tr>
  <tr>
    <td align="center">塔罗：切牌后牌背在她身前展开，点一张或说「你来抽」</td>
    <td align="center">三张落位，点牌背才翻，她只讲翻开的那一张</td>
  </tr>
  <tr>
    <td><img src="./companion/docs/screenshots/tarot-card.jpg" alt="塔罗：翻开倒吊人，她用自己的口吻讲" /></td>
    <td><img src="./companion/docs/screenshots/tarot-dock.jpg" alt="塔罗：九种牌阵可选" /></td>
  </tr>
  <tr>
    <td align="center">翻开的牌推到镜头前，80 张国风牌面 AI 原创；解读先接情绪，不讲算命</td>
    <td align="center">日抽、是否、三张阵、二选一、关系 / 事业五张、凯尔特十字</td>
  </tr>
  <tr>
    <td><img src="./companion/docs/screenshots/cam-review.jpg" alt="镜头审查面板" /></td>
    <td><img src="./companion/docs/screenshots/settings.jpg" alt="设置：体验模块开关" /></td>
  </tr>
  <tr>
    <td align="center">镜头审查：景别 × 运镜 × 站位 × 动作三万多组合逐条标可用 / 不可用</td>
    <td align="center">记忆、情境、重写、证物、塔罗都是可开关模块，关掉等于没装</td>
  </tr>
  <tr>
    <td><img src="./companion/docs/screenshots/keepsake-snow.jpg" alt="证物：雪夜街道" /></td>
    <td><img src="./companion/docs/screenshots/keepsake-room.jpg" alt="证物：卧室情境" /></td>
  </tr>
  <tr>
    <td align="center">证物相册里的舞台截图：情境卡换背景与灯光</td>
    <td align="center">同一角色、另一场戏</td>
  </tr>
</table>

截图中的角色模型来自模之屋作者，仅作演示，版权归原作者。

## 这个仓库里有什么

| 目录 | 说明 |
|---|---|
| [`companion/`](./companion) | **主产品**：Vue 前端 + FastAPI 后端 + Electron 桌面壳 |
| [`companion/docs/`](./companion/docs) | 产品与设计文档：人设怎么写、提示词分层、塔罗玩法与牌面规范、原创歌词 |
| [`companion-3d/`](./companion-3d) | 早期 3D 舞台原型：VRM / GLB / PMX 加载、表情、VMD 舞蹈 |
| [`music-api/`](./music-api) | 独立的学习用音乐检索接口（数据源：爱听音乐网） |

日常使用请跑 `companion/`。`companion-3d` 可以单独打开，用来对照渲染和动作管线。

仓库提交 **完整源码**、情境卡背景 / 舞台贴图、以及整套 AI 原创塔罗牌面。3D 模型、VMD、音乐、语音权重、SQLite、密钥都不入库，克隆后按下面「快速开始」跑起来，再从资产中心导入自己的角色即可。

要打成双击即开的本地 exe（自带 Chromium 窗口、Python 运行时、模型与权重），见 [`companion/README_BUILD.md`](./companion/README_BUILD.md)。

## 体验包（不用自己编译）

网盘里是已经打好的 Windows 包，解压就能开。里面有 **A / B 两份 7z**，以及一份 **一体包**：

[xiaoke.ai 3D本地陪聊 · 百度网盘](https://pan.baidu.com/s/1Y3KuQWG761eP08Uktx36Eg?pwd=xkai)　提取码：`xkai`

| 你下到的 | 是什么 | 怎么开 |
|---|---|---|
| `xiaoke-ai-A-….7z` | **A 程序包**：窗口、代码、瘦 Python。日常换版本只换这个 | 和 B 解压到**同一层目录**，双击 A 里的 `xiaoke-ai.exe` |
| `xiaoke-ai-B.7z` | **B 资源包**：角色、动作、歌曲、离线语音、PyTorch/CUDA。很少重下 | 解压后目录里能看到 `xiaoke-content.json` |
| `xiaoke-ai-20….7z`（没有 `-A` / `-B`） | **一体包**：程序和资源打在同一个文件夹 | 解压后直接双击 `xiaoke-ai.exe`，不用选 B |

用 [7-Zip](https://www.7-zip.org/) 解压。A 和 B 不要一套再套一层，正确样子是：

```
某盘:\xiaoke\
  xiaoke-ai-A-20260904233641\   ← 双击这里的 xiaoke-ai.exe
    xiaoke-ai.exe
  xiaoke-ai-B\
    xiaoke-content.json
```

**第一次开 A**：设置 → 资源包 → 选旁边的 `xiaoke-ai-B` 文件夹（看到 `xiaoke-content.json` 就对了）→ **关掉窗口再开一次**。路径会记在 A 目录的 `content.path`，以后只换新 A 时把这个文件拷过去即可。一体包跳过这一步。

打包版自己带 Chromium，不用再开浏览器。本机端口是后端 `127.0.0.1:5201`、前端 `127.0.0.1:5211`。

- Windows 10+。本地 Qwen TTS 建议有 NVIDIA 显卡和驱动；没有显卡：设置 → 语音 → TTS 改成 edge-tts。
- 包里**不含**聊天密钥。设置 → AI 对话里填 OpenAI 兼容的 `base_url` / `api_key` / `model`。不填也能看舞台、跳舞、听本地兜底回复。
- 请勿删除 A 里的 `electron/`、`runtime/`。3D 角色版权归原作者，仅供个人体验。

自己从源码打包见 [`companion/README_BUILD.md`](./companion/README_BUILD.md)。

## 能做什么

### 舞台与表演

- **3D 舞台**：PMX（MMD）、VRM、GLB 热切换；MMD 带 ammo.js 布料物理（头发、裙摆、飘带）。
- **对话表演**：LLM 流式输出里夹 `[emo:]` `[act:]` `[dance:]` `[cam:]` 标签，实时切表情、动作、舞蹈和运镜。没有 API Key 时走本地兜底，表演链路仍可用。
- **镜头审查**：景别 × 运镜 × 站位 × 动作资产逐条打分，只让审过的组合进剧目，避免镜头穿模或动作错位。
- **实时动捕**：摄像头直播，或选本地视频反复测。MediaPipe Holistic 在 Worker 里检全身、双手、面部，再驱动当前角色。求解思路参考 [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)。

### 对话与声音

- **分层人设**：角色卡只写身份和说话方式；场景包、扮演叠层、时间槽、记忆、导演手册由后端每轮重新拼接。支持「扮演老师」这类临时叠层，能进能出，不污染长期人设。内置角色「清宵」可直接开聊。
- **全双工语音**：一边听一边说，按句排队或打断，沉默后续聊 / 主动搭话。ASR / TTS 可分开选在线或离线。在线：浏览器 Web Speech + edge-tts / 百炼 CosyVoice；离线：SenseVoice-Small + Qwen3-TTS 本地流式。口型跟真实振幅走，屏幕上有同步字幕。
- **重说**：对同一句话换个说法再答一遍，表演标记照常给。
- **长期记忆**：对话里抽出偏好、关系、约定，经 mem0 + 向量库召回后注入下一轮 prompt；扮演和看牌过程默认不入库。

### 一起玩

- **塔罗**：不是弹窗小游戏，是「她坐在你对面给你抽牌」。牌背从台面升起围一圈，抽中的牌飞到她和镜头之间翻开，她用自己的口吻一张一张讲。日抽、是否、过去现在未来、现状阻碍建议、身心、二选一、关系五张、事业五张、凯尔特十字。发牌与正逆位由代码决定，模型不许改；整套 80 张国风牌面 AI 原创，随仓库提供。定位是心理视角与娱乐文创，不讲算命。
- **情境卡**：内置「今晚这场戏」（雨夜小巷、刚吵完、花树下等），也可按记忆生成当晚情境。
- **证物相册**：舞台截图和短片（mediabunny 编码），按角色归档。
- **对话记录**：侧边抽屉回看本场对话与后端 talk log。
- **Code 伴侣**：对话栏点「码」，看着 Cursor 开工、写着、写完，她跟着演。默认盯本机 transcript，可选装钩子。Codex 稍后。

### 资产与角色

- **资产中心**：本地导入 zip / rar / 单文件（解压、乱码文件名修复、PMX / VMD / 音频自动入库）；可对接[模之屋](https://www.aplaybox.com/)在线搜索下载。
- **角色卡**：模型 + 人设 + 音色 + 情绪到形态键的映射 + 闲置动作。
- **模块开关**：记忆、情境、重说、证物、塔罗、Code 伴侣都可以在设置里独立关掉，关掉等于没装。

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
| 语音前端 | Web Speech API、[@ricky0123/vad-web](https://github.com/ricky0123/vad)（Silero VAD）、AEC3 回声消除 |
| 短片 | [mediabunny](https://github.com/Vanilagy/mediabunny) |

引擎代码在 `companion/frontend/src/engine/`（舞台、角色、动作、表情、口型、镜头、闲置、`StagePlugin` 插件口）；功能模块在 `features/`（聊天、语音、表演、资产、角色、动捕、记忆、情境、证物、塔罗、镜头审查）。

### 后端（`companion/backend`）

| 层 | 选用 |
|---|---|
| 服务 | Python 3.11、FastAPI、uvicorn、SQLModel（SQLite） |
| 对话 | OpenAI 兼容 HTTP（可接通义、DeepSeek、火山方舟等）；`prompt_stack` 每轮分层拼接 |
| 记忆 | [mem0](https://github.com/mem0ai/mem0) + 本地 [Qdrant](https://qdrant.tech/)；向量可用云端 embedding 或本机 MiniLM |
| ASR | [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 跑 [SenseVoice-Small](https://github.com/FunAudioLLM/SenseVoice) |
| TTS | [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 本机流式；备选 [edge-tts](https://github.com/rany2/edge-tts)、阿里云百炼 CosyVoice |
| 玩法 | `modules/tarot` 发牌机 + 仪式状态机；`modules/scenes`、`memory`、`rewrite`、`keepsake` 同一套可开关模块 |

### 桌面壳（`companion/desktop`、`build_exe.py`）

Electron 自带 Chromium 窗口；PyInstaller 把启动器打成单文件 exe，同时拉起前后端。发行目录含 Python 运行时、后端字节码、前端压缩包、模型与语音权重，目标机不装 Chrome、不装 Python 也能双击开。

## 快速开始

前置：Windows、Node.js 18+、Python 3.11+。有 NVIDIA 显卡时，本地 Qwen3-TTS 会舒服很多；没显卡走在线语音也完整可用。

日常开发请自己开两个终端，不要用 Cursor 里的后台任务代开（关掉会话时进程容易变成孤儿）。

### 启动

**终端 1 · 后端**（http://127.0.0.1:8600）

```bat
cd companion\backend
set NO_PROXY=*
set PYTHONUNBUFFERED=1
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8600
```

PowerShell 把前两行换成：

```powershell
$env:NO_PROXY='*'; $env:PYTHONUNBUFFERED='1'
```

**终端 2 · 前端**（http://localhost:5175）

```bat
cd companion\frontend
npm run dev
```

浏览器打开 http://localhost:5175 。设置里填 OpenAI 兼容的 `base_url` / `api_key` / `model` 才能真正聊天。

注意：

- 后端**不要**加 `--reload`，也**不要** `--workers N`。改 Python 后在终端 1 里 Ctrl+C 再重新跑上面那条 uvicorn。
- 首次需要虚拟环境和依赖时：`python -m venv .venv`，再 `.venv\Scripts\pip install -r requirements.txt`；前端 `npm install --legacy-peer-deps`。也可以在 `companion/` 下跑一次 `start.bat` 装依赖并开两个窗口。

### 停止

两个终端里各按 **Ctrl+C**。若端口还被占（刷新页面连上旧进程），在 PowerShell 里清掉：

```powershell
foreach ($port in 8600, 5175) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { taskkill /PID $_.OwningProcess /T /F }
}
```

打开后舞台是空的很正常：把 PMX / VRM / GLB 拖进资产中心即可。离线 ASR / TTS 首次点「准备模型」会下载权重，不要把 `companion/backend/data/` 提交上来。

## 文档索引

| 文档 | 内容 |
|---|---|
| [`companion/README.md`](./companion/README.md) | 配置、标签协议、常见问题 |
| [`companion/README_BUILD.md`](./companion/README_BUILD.md) | 打包成可双击运行的 exe 目录 |
| [`companion/docs/persona-guide.md`](./companion/docs/persona-guide.md) | 角色卡怎么写：底设短、规则按场景挂载、扮演单独一层 |
| [`companion/docs/persona-stack.md`](./companion/docs/persona-stack.md) | 每轮 system 分层拼接的实现与取舍 |
| [`companion/docs/personas/`](./companion/docs/personas) | 可直接粘贴的人设正文（清宵、通用） |
| [`companion/docs/tarot.md`](./companion/docs/tarot.md) | 塔罗定位、合规边界、仪式流程、与舞台的接法 |
| [`companion/docs/tarot-cards.md`](./companion/docs/tarot-cards.md) | 80 张国风牌面的逐张设计与出图规范 |
| [`companion/docs/songs/`](./companion/docs/songs) | 舞台用的原创国风歌词 |

## 致谢

这个项目站在很多人已经铺好的路上。若有遗漏，欢迎指出。

### 模之屋，以及各位作者

舞台上能看见、能跳、能做表情，首先要感谢 **[模之屋](https://www.aplaybox.com/)**（aplaybox）。

我们用到的 3D 模型、形态键表情、VMD 动作、镜头文件，几乎全部来自模之屋：既是检索和下载的入口，也是 MMD 作者们长期分享作品的地方。没有这个站点，陪玩舞台会是空的。

同时感谢所有在模之屋发布过模型、表情、动作、镜头的作者。你们的作品让角色真正「活」在浏览器里。版权仍归各位作者本人；二次创作请保留借物表，遵守各作品自带的使用规则，禁止二次配布和商业使用。请勿把模之屋 token 提交进仓库。

### 算法与产品思路

- **小冰（Xiaoice）**  
  全双工语音交互的产品与工程思想：一边听一边说、按句排队或打断、沉默后续聊 / 主动搭话 / 告别。我们的对话节奏（`DuplexCmd`、句子类型、Pool 播或不播）直接借鉴了小冰 这一侧，而不是把整段回复锁死再播完。
- **豆包（Doubao）**  
  多段 system 每轮动态拼接、账号级人设与会话级扮演分层、记忆护栏、代码侧拦截优先于 prompt 文本。我们的 `prompt_stack` 按公开行为反推了这套组织方式，详见 [`persona-stack.md`](./companion/docs/persona-stack.md)。
- **[AmyangXYZ](https://github.com/AmyangXYZ) / [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)**（曾用名 MiKaPo）  
  浏览器里把 MediaPipe 关键点解成 MMD 骨骼父空间四元数：静止时 `parent → child` 世界方向当作参考，每帧 shortest-arc，再用 witness 补手臂/大腿扭转。我们的动捕求解器直接借鉴了这条管线，并在 `companion/frontend/src/features/mocap/` 里按 PMX / VRM / GLB 做了适配。没有 MiPo，这条路会绕很远。
- **Géry Casiez, Nicolas Roussel, Daniel Vogel** — [1€ Filter](https://gery.casiez.net/1euro/)（CHI 2012）  
  动捕平滑用的 One-Euro：静止压抖、快动时放宽截止。
- **樋口优 / MikuMikuDance**  
  PMX、VMD、形态键和刚体物理这一整套 MMD 工作流，是舞台能「跳起来」的前提。
- **pixiv / VRoid**  
  VRM 规范让非 MMD 角色也能用同一套表情和骨骼语义。
- **韦特塔罗传统**  
  牌名、编号与符号沿用传统体系；牌面构图和上色全部原创重绘，不描韦特彩图。

### 开源引擎与库

- **[mrdoob](https://github.com/mrdoob) / [Three.js](https://github.com/mrdoob/three.js)** — Web 三维渲染。
- **[pixiv](https://github.com/pixiv) / [three-vrm](https://github.com/pixiv/three-vrm)** — VRM 加载、表情、弹簧骨。
- **[Poimandres](https://github.com/pmndrs) / [three-stdlib](https://github.com/pmndrs/three-stdlib)** — 新版 Three 拆出去的 `MMDLoader`、`MMDAnimationHelper`、`MMDPhysics`。
- **[ammo.js](https://github.com/kripken/ammo.js)**（Bullet Physics 的 wasm 端口）— MMD 头发、裙摆、飘带。
- **[Google MediaPipe](https://ai.google.dev/edge/mediapipe)** — Holistic 全身 + 双手 + 面部关键点。
- **[Evan You](https://github.com/yyx990803) / Vue、Vite、Pinia** — 前端骨架。
- **[TuSimple / Naive UI](https://github.com/tusen-ai/naive-ui)** — 设置、资产、角色等面板。
- **[Sebastián Ramírez](https://github.com/tiangolo) / FastAPI、SQLModel** — 后端与 SQLite。
- **[Electron](https://www.electronjs.org/)**、**[PyInstaller](https://pyinstaller.org/)** — 桌面窗口壳与单文件启动器。
- **[Vanilagy / mediabunny](https://github.com/Vanilagy/mediabunny)** — 证物短片在浏览器里编码。
- **[ricky0123 / vad-web](https://github.com/ricky0123/vad)**、**[Silero VAD](https://github.com/snakers4/silero-vad)**、**[ONNX Runtime](https://onnxruntime.ai/)** — 开麦时在浏览器切语音段。
- **WebRTC AEC3** — 开麦时抵消她自己的声音。

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

## 协议

源码采用 **[PolyForm Noncommercial License 1.0.0](./LICENSE)**：

- 可以：免费使用、学习、修改、再分发（含修改版），个人、学校、科研机构、公益组织、政府机构使用不受限。
- 不可以：任何商业用途（卖软件、卖服务、内嵌进商业产品、用它引流变现等）。
- 再分发时保留 `LICENSE` 文件和其中的 `Required Notice:` 一行。
- 想商用请先联系作者另行授权。

第三方 3D 模型、动作、音乐、音色不在本协议内，版权归各原作者。仓库自带的塔罗牌面、情境卡背景由本项目 AI 生成，随源码同一协议。

## 说明

- 欢迎 fork、改造、自部署；也欢迎回来提 Issue 和 PR。
- 3D 模型、动作、音乐、音色均有各自版权，不随本仓库转让；请自行确认每一份资产的授权。
- 塔罗玩法定位为心理视角与娱乐文创，仅供娱乐，不构成任何建议。
- 模之屋、音乐站等第三方接口可能随时变更或要求登录，不保证长期可用。
- LLM / TTS / ASR 会把对话或语音发到你配置的服务商，请自己看对方的隐私条款。
