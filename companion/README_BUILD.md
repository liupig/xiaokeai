# 打包成可双击运行的目录

打成两包：

- **A 程序包**：代码、瘦 Python、Electron 窗口。日常改这个。不含 PyTorch。
- **B 资源包**：角色、动作、镜头、歌曲、SenseVoice、Qwen3-TTS、记忆向量、**PyTorch/CUDA**。基本不重打。

产物不进仓库，默认输出到与 `games` 同级。盘不够时先设 `XIAOKE_OUT`（例如 `H:\xiaoke-ai-packs`）。

已经打好的体验包（A / B 两份 7z + 一体包）在网盘，用法见仓库根目录 [README · 体验包](../README.md#体验包不用自己编译)：

https://pan.baidu.com/s/1Y3KuQWG761eP08Uktx36Eg?pwd=xkai　提取码 `xkai`

## 1. 准备

- Windows、已能跑通 `start.bat` 的开发环境
- Node.js（打包机用来下载 Electron）
- 后端 venv 已装 torch / qwen-tts / sherpa-onnx
- 打 B 时还需要：`companion/assets/` 里的角色和动作，以及 `companion/backend/data/speech/` 权重
- [7-Zip](https://www.7-zip.org/)（默认找 `D:\BingSoft\7-Zip\7z.exe`）

## 2. 打包

在 `companion` 目录：

```bat
backend\.venv\Scripts\python.exe build_exe.py
backend\.venv\Scripts\python.exe build_exe.py --content
backend\.venv\Scripts\python.exe build_exe.py --all
backend\.venv\Scripts\python.exe build_exe.py --full
backend\.venv\Scripts\python.exe build_exe.py --skip-7z
set XIAOKE_OUT=H:\xiaoke-ai-packs
backend\.venv\Scripts\python.exe build_exe.py --full
```

| 命令 | 结果 |
|---|---|
| 默认 | 只打 A |
| `--content` / `--b` | 只打 B |
| `--all` | A 和 B 都打 |
| `--full` | 旧的一体包（代码+资源打在同一个目录） |

## 3. 产物

```
E:\BingCode\bingGames\
  xiaoke-ai-A-YYYYMMDDHHMMSS/    ← 程序包
    xiaoke-ai.exe
    electron/  runtime/  app/  web/
    assets/tarot/               牌面（小）
    data/app.db                 审查 + 角色卡（不含密钥/聊天）
    content.path                第一次选完 B 后自动生成
  xiaoke-ai-B/                   ← 资源包（固定名，可覆盖更新）
    xiaoke-content.json
    assets/models|motions|cameras|audio|music
    data/speech                 SenseVoice + Qwen3-TTS
    data/embed                  MiniLM / fastembed
    runtime/Lib/site-packages/torch   本地 Qwen TTS（约 5–7GB）
  xiaoke-ai-YYYYMMDDHHMMSS/      ← --full 一体包（旧，资源打在一起）
```

第一次打开 A：设置 → 资源包 → 选 B 目录（能看到 `xiaoke-content.json`），关掉窗口再开。路径写在 A 的 `content.path`，换新 A 把这个文件拷过去即可。

旧的一体包（A 自己带着 models / speech）仍能直接开，不必选 B。

## 4. 代码保护

- 启动器打进单文件 exe，同时拉起前端 + 后端 + 内嵌 Chromium
- 打包端口：前端 **5211**、后端 **5201**
- 后端 `.pyc`，前端 Vite + Terser

## 5. 注意

- 不要把 `companion/.env` 打进 A
- 不要把 `xiaoke-ai-*` 拷回 `games/` 仓库
- 请勿删除 A 里的 `electron/`
- 目标机本地 Qwen TTS 需要 NVIDIA 驱动；没显卡可用在线语音
