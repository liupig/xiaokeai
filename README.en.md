# xiaoke.ai

A locally hosted, desktop-class companion: pick or download a 3D character, set persona and voice, then talk in text or speech. She sits across from you — voice, lip-sync, expression, motion, and dance.

This repo is for learning and personal use, not commercial distribution. Bundled models, motions, and music remain copyright of their original authors. Follow each asset’s own terms.

[中文](./README.md) · [xiaoke.ai](https://xiaoke.ai)

## What’s in this repo

| Path | What it is |
|---|---|
| [`companion/`](./companion) | **Main product**: Vue frontend + FastAPI backend |
| [`companion-3d/`](./companion-3d) | Early 3D stage prototype (VRM / GLB / PMX, expressions, VMD) |
| [`music-api/`](./music-api) | Standalone research music search API |

Use `companion/` day to day. `companion-3d` is a smaller sandbox for the render and motion pipeline.

This repo ships **demo source** plus scene-card backgrounds / stage textures. 3D models, VMD, music, speech weights, SQLite, and API keys stay local. After `start.bat`, import your own character in the asset hub.

A ready-to-run Windows pack (program A + content B as two 7z files, plus a monolithic all-in-one 7z) is on [Baidu Netdisk](https://pan.baidu.com/s/1Y3KuQWG761eP08Uktx36Eg?pwd=xkai) (password `xkai`). Extract, then double-click `xiaoke-ai.exe`. For A+B, pick the B folder once under Settings → Content pack (look for `xiaoke-content.json`) and restart. The all-in-one folder needs no extra step. Details in Chinese: [README · 体验包](./README.md#体验包不用自己编译).

## What it does

- **3D stage**: hot-swap PMX (MMD), VRM, and GLB; MMD cloth physics via ammo.js.
- **Live mocap**: webcam, or a local video for repeatable tests. MediaPipe Holistic runs in a Worker (body, both hands, face). The IK-style solver follows [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo).
- **Performed chat**: the LLM streams tags such as `[emo:]` `[act:]` `[dance:]` `[cam:]`. No API key still gets a local fallback so dance / face / motion still work.
- **Speech loop**: ASR and TTS can each be online or offline. Online: Web Speech + edge-tts / DashScope CosyVoice. Offline: SenseVoice-Small + Qwen3-TTS (local streaming). Lips follow real amplitude.
- **Long-term memory**: facts (preferences, people, promises) extracted into mem0 + a local vector store, then injected into later prompts.
- **Scene cards**: “tonight’s scene” (rain alley, after a fight, under the blossoms, …), or a card generated from memory.
- **Keepsakes**: stills and short clips from the stage (encoded with mediabunny).
- **Asset hub**: import zip / rar / single files; optional search and download from [aplaybox](https://www.aplaybox.com/).
- **Character cards**: model + system prompt + voice + emotion morph map + idle motion.

Setup, tag protocol, and troubleshooting: [`companion/README.md`](./companion/README.md) (Chinese).

## Stack

**Frontend** — Vue 3, TypeScript, Vite, Pinia, Naive UI, [Three.js](https://threejs.org/), [@pixiv/three-vrm](https://github.com/pixiv/three-vrm), [three-stdlib](https://github.com/pmndrs/three-stdlib) (MMDLoader / MMDPhysics) + ammo.js, [MediaPipe Holistic](https://ai.google.dev/edge/mediapipe/solutions/vision/holistic_landmarker), [@ricky0123/vad-web](https://github.com/ricky0123/vad), [mediabunny](https://github.com/Vanilagy/mediabunny).

**Backend** — Python 3.11, FastAPI, SQLModel (SQLite), OpenAI-compatible LLM HTTP, [mem0](https://github.com/mem0ai/mem0) + local [Qdrant](https://qdrant.tech/), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) + [SenseVoice](https://github.com/FunAudioLLM/SenseVoice), [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), [edge-tts](https://github.com/rany2/edge-tts), DashScope CosyVoice.

## Quick start

Needs Windows, Node.js 18+, Python 3.11+. A NVIDIA GPU helps local Qwen3-TTS.

Use two terminals of your own. Do not leave the servers as Cursor background jobs (they often survive as orphans after the chat ends).

**Terminal 1 · backend** (http://127.0.0.1:8600)

```bat
cd companion\backend
set NO_PROXY=*
set PYTHONUNBUFFERED=1
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8600
```

PowerShell: `$env:NO_PROXY='*'; $env:PYTHONUNBUFFERED='1'` then the same uvicorn line.

**Terminal 2 · frontend** (http://localhost:5175)

```bat
cd companion\frontend
npm run dev
```

Do **not** pass `--reload` or `--workers`. After Python changes, Ctrl+C in terminal 1 and start uvicorn again. Stop with Ctrl+C in both terminals. If a port is still held:

```powershell
foreach ($port in 8600, 5175) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { taskkill /PID $_.OwningProcess /T /F }
}
```

Open http://localhost:5175. Fill an OpenAI-compatible `base_url` / `api_key` / `model` in Settings for real chat. An empty stage is expected until you import a PMX / VRM / GLB. Offline ASR / TTS weights download on first “prepare model”; do not commit `companion/backend/data/`. First-time deps: `python -m venv .venv` then pip/npm, or run `companion\start.bat` once.

## Acknowledgements

We stand on work other people already shipped. Please tell us if we missed someone.

### aplaybox, and every author there

The stage would be empty without **[模之屋 / aplaybox](https://www.aplaybox.com/)**.

Almost every 3D model, facial morph, VMD motion, and camera file we use comes from aplaybox: it is both the search/download door and the place MMD authors have been sharing work for years.

We also thank every author who published models, expressions, motions, or cameras there. The characters only “live” in the browser because of that work. Copyright stays with each author. Keep credit lists, follow each work’s own terms, and do not redistribute or use commercially. Do not commit an aplaybox token to this repo.

### Ideas and algorithms

- **Xiaoice (小冰)** — full-duplex spoken interaction: listen while speaking, queue or barge-in per sentence, then delayed continue / proactive / goodbye after silence. Our dialogue timing (`DuplexCmd`, sentence types, play-or-skip) follows Xiaoice’s Processor / side, instead of locking a whole reply before playback.
- **[AmyangXYZ](https://github.com/AmyangXYZ) / [Reze MiPo](https://github.com/AmyangXYZ/reze-mipo)** (formerly MiKaPo) — MediaPipe landmarks → MMD parent-local quaternions: rest `parent → child` as the reference, shortest-arc per frame, witness bones for arm/thigh roll. Our solver in `companion/frontend/src/features/mocap/` is adapted from that pipeline.
- **Géry Casiez, Nicolas Roussel, Daniel Vogel** — [1€ Filter](https://gery.casiez.net/1euro/) (CHI 2012), used to smooth mocap.
- **Higuchi Yu / MikuMikuDance** — PMX, VMD, morphs, and rigid-body physics.
- **pixiv / VRoid** — the VRM spec.

### Engines and libraries

Three.js (mrdoob), three-vrm (pixiv), three-stdlib (Poimandres), ammo.js / Bullet, Google MediaPipe, Vue / Vite / Pinia (Evan You), Naive UI, FastAPI / SQLModel (Sebastián Ramírez), mediabunny, vad-web, Silero VAD, ONNX Runtime.

### Models, memory, speech

mem0, Qdrant, Hugging Face / MiniLM, Qwen / Qwen3-TTS, FunAudioLLM SenseVoice, k2-fsa sherpa-onnx, edge-tts, Alibaba DashScope CosyVoice, ModelScope.

## Notes

Code is for study, research, and personal deployment. Third-party models, motions, and music are not relicensed by this repo. aplaybox and similar sites may change or require login. LLM / TTS / ASR send data to whichever provider you configure.
