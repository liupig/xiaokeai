# 3D 陪聊角色 Demo

基于 Three.js 的网页版 3D 角色演示，支持 VRM / GLB / MMD(PMX) 三种模型格式：

- 镜头切换：近景 / 半身 / 全身（平滑过渡）
- 说话口型：嘴巴自动开合（后续可接 TTS 语音驱动）
- 自动眨眼、呼吸、身体轻微摆动
- 表情：自然 / 开心 / 生气 / 伤心 / 放松
- 动作：挥手 / 点头 / 摇头
- 眼睛始终看向镜头，鼠标可自由旋转视角

## 运行

```bash
npm install
npm run dev
```

打开 http://localhost:5173

本目录不随仓库分发 3D 模型和 VMD（版权与体积）。把文件放进 `public/models/`、`public/motions/` 后再打开页面。

## 更换角色模型

仓库里没有预置角色。把 `.vrm` / `.glb` / `.pmx` 放到 `public/models/`，再用 URL 参数 `?model=` 指定（相对 `public/models/`）：

- `?model=qingxiao/model.pmx` — PMX 示例（默认路径，需自行放入对应文件）
- `?model=avatar` — VRM（会补 `.vrm` 后缀）
- `?model=someone.glb` — 写实风 GLB（ARKit 表情）

想加自己的角色：

- VRM：用 [VRoid Studio](https://vroid.com/studio)（免费）捏人导出
- PMX：各 MMD 模型站下载（注意目录里要带 textures 等贴图文件夹）

表情、口型、手臂放下姿势会自动适配（VRM 标准表情 / ARKit 形态键 / MMD 日文形态键）。

## 播放专业动作（VMD，仅 MMD 模型）

程序化动画比较机械，想要自然的动作可以加载 VMD 动作文件（MMD 生态的 K 帧动作，
IK、表情、镜头感都是专业调的）：

```
http://localhost:5173/?model=qingxiao/model.pmx&motion=dance.vmd
```

- 动作文件放在 `public/motions/` 下，并把文件名加进 `public/motions/motions.json` 清单
- 页面右上角"表情 / 动作库"抽屉里可以随时播放、切换、停止任何动作
- 也可以用 `?motion=文件名` 在打开页面时直接播放
- `motions.json` 是清单模板（仓库不含 .vmd 文件），格式支持 `{ "file": "xxx.vmd", "label": "中文名" }`
- 更多动作：[aplaybox 动作区](https://www.aplaybox.com/model/motion)、bowlroll 等，
  下载 `.vmd` 文件放进 `public/motions/` 即可；推荐找"待机""idle"类动作做陪聊闲置姿态
- 播放 VMD 期间程序化身体动画（呼吸/挥手/点头）自动让位，表情按钮仍可用

## 表情库 / 动作库面板

右上角"表情 / 动作库"按钮打开抽屉：

- **表情库**：自动列出模型自带的全部形态键（清宵有 130 个，含眨眼、星星眼、
  脸红、流泪、爱心眼、各种口型等），点击开/关，支持多个叠加、搜索、一键重置
- **动作库**：列出 `motions.json` 里的全部 VMD 动作，点击即播，可随时切换或停止回到闲置

## 技术栈

- [Three.js](https://threejs.org/) — 3D 渲染
- [@pixiv/three-vrm](https://github.com/pixiv/three-vrm) — VRM 角色加载与表情/骨骼控制
- [three-stdlib](https://github.com/pmndrs/three-stdlib) — MMDLoader / MMDPhysics（新版 three 已移除，由该包提供）
- ammo.js（Bullet 物理引擎 wasm 版，`public/libs/`）— MMD 头发/飘带/裙摆物理模拟
- Vite + TypeScript

## 后续可扩展

- 接入大模型 API 实现真实对话（聊天框 UI + LLM）
- 接入 TTS 语音合成，用音量驱动口型（替换现在的正弦波模拟）
- 用 Mixamo 动作库或 VRMA 动画文件替换程序化动作
- 场景美化：房间环境、HDR 光照、后期效果
