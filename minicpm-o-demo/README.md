# MiniCPM-o 4.5 独立小 Demo

和 xiaoke 主程序**完全分开**：自己的 `.venv`、自己的权重目录。不会改 companion 里的 `transformers 4.57` / Qwen TTS。

这是「听进去、模型自己懂、再说话」的合并链路，不是 SenseVoice → LLM → TTS 三段。

## 你这台机器怎么跑

| 路径 | 显存 | 怎么开 |
|---|---|---|
| **GGUF Q4 听+说**（推荐，8GB 卡：关掉视觉、ctx=1024、KV q4） | 约 6–7GB | 权重用 `setup.ps1 gguf`，再把 Comni 的 `llama-server.exe` 放到 `bin\comni` |
| **PyTorch 4bit / AWQ**（没编译 C++ 时的退路） | 约 11GB | `setup.ps1 awq`，启动后自动走这条 |

官方 GGUF 引擎不在 pip 里。预编译桌面版是 [Comni](https://github.com/tc-mb/llama.cpp-omni/releases)（Windows 安装包）。也可以自己编 [llama.cpp-omni](https://github.com/tc-mb/llama.cpp-omni) 的 `llama-omni-server`。找不到 exe 时，Demo 会改用本目录 venv 里的 PyTorch。

## 一次性安装

在 PowerShell 里：

```powershell
cd minicpm-o-demo
# 只下 GGUF Q4 全套（约 8GB，国内走 ModelScope）
.\setup.ps1 gguf

# 没有 llama-omni-server 时，再下一份 AWQ 才能用 PyTorch 退路
.\setup.ps1 awq
```

`setup.ps1` 会新建 `.venv`，并按官方要求安装 `torch==2.8.0` + `transformers==4.51.0`。

## 启动

先**关掉** xiaoke 主窗口（Qwen TTS 会占显存）。

```powershell
cd minicpm-o-demo
.\start.ps1
```

浏览器打开 http://127.0.0.1:8765

1. 点「加载模型」
2. **按住说话**，松开等它回（当前不加载视觉，只听+说）

## 目录

```
minicpm-o-demo/
  .venv/          独立环境，勿和 companion 混用
  models/         GGUF / AWQ 权重
  bin/            放置 llama-omni-server.exe
  assets/ref.wav  克隆音色用的参考音频
  output/         合成的 wav
```

环境变量 `LLAMA_OMNI_SERVER` 可指向已有的 server 可执行文件。
