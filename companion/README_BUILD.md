# 打包成可双击运行的 exe 目录

做法对齐 `zhixiang/v7`：启动器用 PyInstaller 打成 **单文件 exe**（Python 源码在 exe 里）；3D 模型、动作、语音权重、Python 运行时放在 exe 旁边，双击就能开。

产物**不进本仓库**，输出到与 `games` 同级目录，每次一个带秒级时间戳的文件夹，方便留多个版本。

## 1. 准备

- Windows、已能跑通 `start.bat` 的开发环境
- 已安装 Node.js（打包时用 npm 下载 Electron/Chromium 内核，打进发行目录，目标机不用装 Chrome）
- 后端 venv 里已装好 torch / qwen-tts / sherpa-onnx
- `companion/assets/` 里已有角色和动作
- `companion/backend/data/speech/` 里已有 SenseVoice、Qwen3-TTS 权重
- 已安装 [7-Zip](https://www.7-zip.org/)（脚本默认找 `D:\BingSoft\7-Zip\7z.exe`）

## 2. 打包

在 `companion` 目录：

```bat
backend\.venv\Scripts\python.exe build_exe.py
```

时间主要花在拷贝运行时（约数 GB）、语音模型和打 7z 上，请预留磁盘。

## 3. 产物

假设仓库在 `E:\BingCode\bingGames\games`，输出在它的上一级：

```
E:\BingCode\bingGames\
  xiaoke_ai_YYYYMMDDHHMMSS/     ← 可双击运行的完整目录
    CompanionStudio.exe
    使用说明.txt
    electron/                   自带 Chromium 窗口内核（不需要安装 Chrome）
    runtime/                    Python + torch/CUDA
    app/                        后端字节码（.py 已删）
    web/                        前端压缩包
    assets/                     3D 模型 / VMD / 音频 / 镜头
    .env.example                空模板（不含 Key；不要把开发机 .env 打进去）
    data/app.db                 镜头审查 + 默认可选角色 + 舞蹈配乐绑定（不含密钥/聊天）
    data/cam_review.json        审查备份
    data/speech/                SenseVoice + Qwen3-TTS
  xiaoke_ai_YYYYMMDDHHMMSS.7z   ← 同上内容的压缩包
  _xiaoke_ai_work/              打包过程中的临时目录，结束后会删
```

把 **整个文件夹** 或 **7z** 拷到目标电脑。双击后打开的是 **自带 Chromium 窗口**（`electron/` 目录，不需要安装 Chrome），页面仍是 **9615** 上的完整舞台 + 聊天；9610 是 API。

## 4. 代码保护

- 启动器打进单文件 exe，双击后 **同时拉起前端 + 后端 + 内嵌 Chromium 窗口**
- 打包端口：前端 **9615**、后端 **9610**（开发环境仍是 5175 / 8600，互不占用）
- Chromium 内核随包分发（Electron），目标机没有 Chrome 也能用
- 后端：`compileall` 成 `.pyc` 后删除 `.py`
- 前端：Vite + Terser 压缩混淆（去 console、混淆标识符）

这不是军事级加密，能挡住随手翻目录、不能挡住专业逆向。

## 5. 注意

- **不要把 `companion/.env` 打进发行包。** 脚本不会拷密钥；目标机在设置面板填 Key，或自己放 `.env`（可参考包里的 `.env.example`）
- 目标机需要 NVIDIA 驱动才能用本地 Qwen TTS；没显卡时舞台和在线语音仍可用
- 不要把 `xiaoke_ai_*` 拷回 `games/` 仓库里
- 请勿删除发行目录里的 `electron/`；那是窗口内核，不是本机 Chrome
