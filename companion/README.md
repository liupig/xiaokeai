# Companion Studio · AI 陪玩

单机部署的 AI 陪玩桌面级 Web 产品：挑选 / 下载 3D 角色，配置人设与声音，通过文本或语音对话；角色用语音 + 口型 + 表情 + 动作 + 舞蹈实时回应。

## 功能一览

- **3D 舞台**：支持 PMX（MMD）/ VRM / GLB 三种模型格式，热切换；MMD 模型带 ammo.js 布料物理（头发/裙摆/飘带）。
- **实时动捕**：右上角摄像机按钮开直播；旁边的影片按钮可选本地视频文件做可重复测试（预览可拖进度 / 循环，不镜像）。MediaPipe Holistic 在 Worker 中检测全身 / 双手 / 面部，实时驱动当前角色（PMX 骨骼最完整，VRM/GLB 走人体骨骼映射）。算法参考 [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)。
- **资产中心**：本地导入 zip/rar/单文件（自动解压、乱码文件名修复、PMX/VMD/音频自动分类入库）；对接模之屋（aplaybox）在线搜索与下载。
- **角色卡**：模型 + 人设（System Prompt）+ 音色 + 情绪映射（每种情绪叠加模型自带形态键）+ 闲置动作。
- **对话表演**：LLM 流式输出内嵌 `[emo:]` `[act:]` `[dance:]` `[cam:]` 标签，实时驱动表情、动作、舞蹈和运镜；无 API Key 时本地兜底应答，表演链路完全可用。
- **语音闭环**：ASR / TTS 分开设置。在线：浏览器 Web Speech + edge-tts / 百炼 CosyVoice；离线：SenseVoice-Small（CPU）+ Qwen3-TTS 本地流式。真实振幅口型同步。
- **长期记忆 / 情境 / 证物**：mem0 抽取并召回长期事实；情境卡设定「今晚这场戏」；舞台截图与短片按角色归档。

## 目录结构

```
companion/
├── frontend/          # Vue 3 + TS + Vite + Pinia + Naive UI + Three.js
│   └── src/
│       ├── engine/    # 3D 引擎层（纯 TS）：stage / avatar / motion / expression / lipsync / camera / idle
│       ├── features/  # 功能模块：chat / voice / performance / assets / character / settings / hud / stage / mocap
│       ├── stores/    # Pinia：character / assets / chat / settings
│       └── api/       # 后端 HTTP / SSE 客户端
├── backend/           # Python 3.11 + FastAPI
│   ├── app/
│   ├── data/          # SQLite / 记忆 / 语音权重（自动创建，已 gitignore）
│   └── requirements.txt
├── assets/            # 资产仓库：models / motions / audio / cameras / music（舞蹈兜底曲库）
└── start.bat
```

## 快速开始（Windows）

前置：Node.js 18+、Python 3.11+。自己开两个终端启动；改完 Python 后要重启后端。

### 启动

**终端 1 · 后端** http://127.0.0.1:8600

```bat
cd backend
set NO_PROXY=*
set PYTHONUNBUFFERED=1
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8600
```

PowerShell：`$env:NO_PROXY='*'; $env:PYTHONUNBUFFERED='1'` 再跑 uvicorn。

**终端 2 · 前端** http://localhost:5175

```bat
cd frontend
npm run dev
```

不要加 `--reload` / `--workers`，否则会复制 ASR、TTS、记忆子进程，抢 SQLite 和显卡。改完后端代码：终端 1 Ctrl+C，再重新启动 uvicorn。

首次没有 `.venv` / `node_modules` 时：

```bat
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt
cd frontend && npm install --legacy-peer-deps
```

也可以直接跑 `start.bat`（会装依赖并弹出两个窗口）。

### 停止

两个窗口各 Ctrl+C。端口仍被占时：

```powershell
foreach ($port in 8600, 5175) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { taskkill /PID $_.OwningProcess /T /F }
}
```

打开 http://localhost:5175 即可使用。仓库不含 3D 模型和动作文件：用资产中心本地导入，或配置模之屋 token 后在线下载。

## 配置指南

### LLM（真实聊天能力）

设置（右上角 ⚙️）→ AI 对话：填 OpenAI 兼容接口的 `base_url` / `api_key` / `model`。
不填 Key 也能用：聊天走本地兜底应答，跳舞/表情/动作/语音全部可用。

### 语音识别 / 合成（可分开选在线或离线）

设置 → 语音：ASR 和 TTS 互相独立。

- **ASR 在线**：Chrome/Edge Web Speech（默认）。
- **ASR 离线**：SenseVoice-Small，CPU 即可。后端需 `pip install sherpa-onnx`，首次点「准备模型」下载约 230MB。
- **TTS 在线**：edge-tts（默认，免费中文）。
- **TTS 离线**：Qwen3-TTS 0.6B。另装 `pip install qwen-tts`（首次加载约 1.2GB，建议 NVIDIA GPU 2–4GB 显存）。

### aplaybox 在线下载

1. 浏览器登录 [模之屋](https://www.aplaybox.com/)。
2. F12 → Application → Cookies → 复制 `token` 的值。
3. 设置 → 下载 → 粘贴 token。
4. 资产中心（📦）→ 在线搜索 → 下载。下载规则（点赞/收藏/关注）会自动满足；若提示"需要图形验证"，是站方风控，稍后再试或到官网手动下载后本地导入。

### 本地导入

资产中心 → 本地导入，拖入 zip / rar / pmx / vrm / glb / vmd 文件即可，自动分类入库。

### 情绪标签协议

LLM 输出内嵌标签驱动表演（后端剥离，不会念出来）：

| 标签 | 说明 |
|---|---|
| `[emo:happy/angry/sad/relaxed/neutral]` | 切换表情（可叠加角色卡自定义形态键） |
| `[act:wave/nod/shake]` | 挥手 / 点头 / 摇头 |
| `[dance:文件名.vmd]` | 播放舞蹈（仅 MMD/PMX 模型支持 VMD） |

## 常见问题

- **模型加载后不可见**：确认浏览器支持 WebGL2；开发时若刚升级过依赖，硬刷新（Ctrl+F5）清掉旧的预打包缓存。
- **高刷新率屏幕物理抽搐**：已内置固定物理步长修正（1/65s 累积推进），无需处理。
- **VMD 播放报错**：VMD 只适用于 MMD/PMX 模型，VRM/GLB 模型会提示不支持。
- **动捕无反应**：摄像头需允许浏览器访问；也可用右上角影片按钮选本地 mp4/webm 测试。首次启动会从 CDN 下载 MediaPipe Holistic 模型（约十余 MB）。全身入镜效果最好，半身时腿会回到静止姿势。动捕开启时会暂停 VMD / 闲置动画。
- **端口占用**：前端 5175、后端 8600（改端口需同步改 `frontend/vite.config.ts` 里的 `BACKEND`）；被占用时先杀掉残留进程再启动，避免旧进程提供过期代码。

## 技术栈

前端 Vue 3 / TypeScript / Vite / Pinia / Naive UI / Three.js 0.185 / three-vrm 3.5 / three-stdlib（MMDLoader + MMDPhysics + ammo.js）/ MediaPipe Holistic（摄像头动捕）/ mediabunny（证物短片）；后端 FastAPI / SQLModel(SQLite) / mem0 + Qdrant / sherpa-onnx SenseVoice / Qwen3-TTS / edge-tts。

仓库根目录 [README](../README.md) 有完整技术说明和致谢名单。

## 致谢

舞台上的模型、表情、动作、镜头几乎全部来自 [模之屋](https://www.aplaybox.com/)，在此统一感谢站点以及所有在那里分享作品的作者。全双工对话节奏借鉴小冰（Xiaoice）的 Jarvis Processor / Transaction。动捕求解借鉴 [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)。完整名单见仓库根目录 [README · 致谢](../README.md#致谢)。
