# xiaoke.ai 完整功能清单

**简体中文** · [English](./features.en.md) · [返回 README](../../README.zh-CN.md)

本文按当前代码和已有功能文档整理，只列已经实现的能力，不包含 TODO、规划中和明确未做的功能。README 是产品概览，本文用于完整核对功能范围。

## 1. AI 对话与模型接入

- **38 个对话服务预设**，另支持自定义 OpenAI 兼容接口。
- 支持 OpenAI、Anthropic、Gemini、DeepSeek、通义千问、豆包、Kimi、智谱、MiniMax、OpenRouter 等服务商。
- 本地模型服务：**Ollama、vLLM、SGLang、Player2**。
- 流式回复、连接测试、思考模式、温度、`top_p`、回复长度设置。
- 无 API Key 时使用本地兜底回复，舞台和表演仍可使用。
- 内置 **DeepSeek Harness（dsh）** 聊天代理。
- Harness 技能：聊天、跳舞、塔罗、绘图、联网查询、视觉陪看、启动游戏。
- 角色会话共享、历史重建、上下文预算控制和会话轮换。

### 38 个对话服务商预设

在 **设置 → AI 对话** 中选择服务商，会自动填写接口地址和推荐模型。密钥仍需换成对应服务商自己的，保存在本机，不写入数据库；留空时可读取系统环境变量或本地 `.env`。也可以不使用预设，手动填写地址和模型名，并通过「测试连接」检查可用性。

Azure、Cloudflare 等地址中包含用户资源名的服务不单独设预设，直接使用自定义兼容接口。

| # | 服务商 | 选中后的推荐模型 |
|---:|---|---|
| 1 | 阿里云百炼（通义千问 / Kimi） | `qwen-plus` |
| 2 | 通义千问国际站 | `qwen-plus` |
| 3 | 火山方舟（豆包） | `doubao-seed-1-6-250615` |
| 4 | 火山方舟（豆包角色） | `doubao-seed-character-260628` |
| 5 | 面壁 MiniCPM-o 4.5 Omni | `MiniCPM-O-4.5-9B` |
| 6 | DeepSeek 官方 | `deepseek-chat` |
| 7 | Moonshot（Kimi 官方） | `kimi-k2-turbo-preview` |
| 8 | Moonshot 国际站 | `kimi-k2-turbo-preview` |
| 9 | 智谱 GLM | `glm-4.5-flash` |
| 10 | 硅基流动 SiliconFlow | `deepseek-ai/DeepSeek-V3` |
| 11 | 阶跃星辰 StepFun | `step-2-mini` |
| 12 | 百川 Baichuan | `Baichuan4-Turbo` |
| 13 | MiniMax | `MiniMax-M2` |
| 14 | 魔搭 ModelScope | `Qwen/Qwen2.5-72B-Instruct` |
| 15 | 腾讯混元 | `hunyuan-turbos-latest` |
| 16 | 小米 MiMo Flash | `mimo-v2.6-flash` |
| 17 | 小米 MiMo Pro | `mimo-v2.6-pro` |
| 18 | AIHubMix | `gpt-4o-mini` |
| 19 | 302.AI | `gpt-4o-mini` |
| 20 | OpenAI | `gpt-4o-mini` |
| 21 | Anthropic Claude | `claude-sonnet-4-5`，使用兼容接口及 Anthropic 请求头 |
| 22 | Google Gemini（OpenAI 兼容） | `gemini-2.0-flash` |
| 23 | OpenRouter | `openai/gpt-4o-mini` |
| 24 | Groq | `llama-3.3-70b-versatile` |
| 25 | Mistral | `mistral-small-latest` |
| 26 | xAI（Grok） | `grok-3` |
| 27 | Together.ai | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| 28 | Fireworks.ai | `accounts/fireworks/models/llama-v3p3-70b-instruct` |
| 29 | NVIDIA NIM | `meta/llama-3.3-70b-instruct` |
| 30 | Cerebras | `llama-3.3-70b` |
| 31 | Perplexity | `sonar` |
| 32 | Novita | `deepseek/deepseek-v3` |
| 33 | CometAPI | `gpt-4o-mini` |
| 34 | Featherless | `meta-llama/Llama-3.3-70B-Instruct` |
| 35 | Ollama，本机 `127.0.0.1:11434` | `llama3.2`；需自行启动 Ollama，不打进体验包 |
| 36 | vLLM，本机 `127.0.0.1:8000` | `default` |
| 37 | SGLang，本机 `127.0.0.1:30000` | `default` |
| 38 | Player2，本机 `127.0.0.1:4315` | `player2` |

对话参数：

| 参数 | 范围 | 作用 |
|---|---|---|
| 思考模式 | 跟随模型默认 / 强制开 / 强制关 | 开启后先推理再回答，首句可能更慢；不支持的模型应改回默认 |
| 温度 | 0–1.5，步进 0.05 | 控制回复的活跃程度 |
| `top_p` | 0.1–1，步进 0.05 | 控制采样范围 |
| 回复长度上限 | 0–32768，步进 256 | 0 表示使用服务商默认值 |

回复采用流式输出；正文中的表演标签会被剥离，不会被朗读。

## 2. 人设、角色卡与世界书

- 分层人设：身份、临时扮演、时间、间隔、记忆、情境、导演规则、边界控制。
- 临时角色扮演可进入、退出，不污染长期人设。
- **27 个中文人设模板**。
- 五档聊天边界，从全年龄到自由模式。
- 每个角色可设置：
  - 绑定模型
  - 人设和开场白
  - 多个备选开场白
  - 音色
  - 情绪到形态键映射
  - 闲置动作偏好
  - 标签和作者信息
- 兼容 **SillyTavern v1/v2/v3 PNG/JSON 角色卡**。
- 兼容 **AICC 角色卡**。
- 导出 **SillyTavern V2 PNG 角色卡**。
- 保留原卡未知字段、作者元数据和扩展信息。
- 支持 Lorebook／世界书：
  - 关键词及正则触发
  - 常驻条目
  - 选择性条目
  - 注入顺序和位置
  - 有限递归触发
  - 注入长度限制
- 独立用户档案，无需改写角色人设。

角色卡格式和 Lorebook 概念来自 [SillyTavern](https://github.com/SillyTavern/SillyTavern) 开放生态及社区角色卡规范；本项目实现兼容导入、分层提示词接入和 3D 舞台呈现。角色卡版权归原作者。

## 3. 语音识别 ASR

共 **7 种**。识别和合成的引擎互相独立。除浏览器 Web Speech 外，均由浏览器中的 Silero VAD 检测说话开始和结束，切出语音段后送去识别。

| # | 引擎 | 运行位置 | 模型、密钥与说明 |
|---:|---|---|---|
| 1 | SenseVoice-Small | **离线，本机 CPU** | 自动识别中 / 英 / 日 / 韩 / 粤；首次点击「准备 / 下载模型」下载约 230MB；独立进程运行，不与 TTS 共用解释器 |
| 2 | 阿里百炼 | 在线 | `qwen3-asr-flash`；与对话共用百炼 `sk-` 密钥 |
| 3 | 火山豆包识别 2.0 | 在线 | 资源 `volc.seedasr.sauc.duration`；可共用方舟 Key，语音鉴权失败时使用 `VOLC_SPEECH_API_KEY` |
| 4 | OpenAI | 在线 | `gpt-transcribe`；可共用对话 Key，也可使用 `OPENAI_API_KEY`；接口地址需指向 OpenAI |
| 5 | ElevenLabs | 在线 | `scribe_v2`；使用 `ELEVENLABS_API_KEY`，识别与朗读共用；不提供对话和向量服务 |
| 6 | Google Gemini | 在线 | `gemini-2.5-flash` 音频理解；可共用对话 Key，也可使用 `GEMINI_API_KEY` |
| 7 | 浏览器 Web Speech | 在线 / 浏览器 | 仅 Chrome / Edge；默认识别方式 |

角色播放声音时，WebRTC AEC3 消除回声。VAD 检测到「开始说话」时，如果仍在播放且当前音量像回声，不会误判为用户开口。

## 4. 语音合成 TTS

共 **9 种，另可关闭**，合计 **300+ 预置音色**。口型跟随真实音频振幅，不按某种语言的音素计算；浏览器系统语音没有真实口型。切换对话语言时会使用该语言记住的音色，只修改界面语言不会改变音色。

| # | 引擎 | 运行位置 | 模型 / 音色 |
|---:|---|---|---|
| 1 | Qwen3-TTS | **离线，本机 GPU 流式 PCM** | 0.6B 或 1.7B，两套共用 9 个音色；建议 NVIDIA GPU |
| 2 | 浏览器系统语音 | 本机 | 使用设备已安装的系统语音；无真实口型 |
| 3 | 小米 MiMo | 在线，24kHz PCM16 流式 | `mimo-v2.5-tts`；9 个预置音色，支持情绪与自由文本指导 |
| 4 | 火山豆包合成 2.0 | 在线 | `seed-tts-2.0`；100 个音色 |
| 5 | 阿里百炼 CosyVoice | 在线流式 | CosyVoice-v3-Flash；88 个龙安 / loong 系列音色 |
| 6 | OpenAI TTS | 在线 | `gpt-4o-mini-tts`；13 个音色，默认 Marin |
| 7 | ElevenLabs | 在线流式 | Flash v2.5；52 个官方预置音色，不含用户克隆音色 |
| 8 | Google Gemini TTS | 在线流式 PCM | `gemini-3.8-flash-lite-tts`；30 个音色，默认 Kore |
| 9 | edge-tts | 在线流式 | 微软神经网络语音；内置 11 个音色 |
| 10 | 关闭语音 | — | 只显示文字，不朗读 |

### 本地 Qwen3-TTS 规格

- **0.6B**：速度更快、显存占用更低。
- **1.7B**：音质更好，权重约 4GB，支持默认、清冷御姐、磁性气声、温柔撩人和自定义语气描述。
- 切换模型大小时会卸载旧模型再加载。
- 清宵建议组合：1.7B + 塞蕾娜 + 清冷御姐。
- 没有合适的 NVIDIA GPU 时可改用 edge-tts。

### 预置音色名单

- **Qwen 9 个：** 薇薇安（明亮少女）、塞蕾娜（温柔女声）、福叔（沉稳男声）、迪伦（北京男声）、艾瑞克（成都男声）、瑞恩（英语男声）、艾登（美式男声）、小野安娜（日语女声）、素熙（韩语女声）。中文和英语默认塞蕾娜，日语默认小野安娜，韩语默认素熙。
- **MiMo 9 个：** 冰糖、茉莉、苏打、白桦、`mimo_default`（中国集群实际为冰糖）、Mia、Chloe、Milo、Dean。
- **edge-tts 11 个：** 晓伊（活泼少女）、晓晓（温柔女声）、云希（少年）、云健（青年男声）、晓北（东北话）、晓臻（台湾腔）、Aria、Jenny、Guy、七海（日语）、SunHi（韩语）。
- **OpenAI 13 个：** Marin、Cedar（官方推荐）、Alloy、Ash、Ballad、Coral、Echo、Fable、Nova、Onyx、Sage、Shimmer、Verse。
- **Gemini 30 个：** Kore、Zephyr、Leda、Aoede、Callirrhoe、Autonoe、Despina、Erinome、Laomedeia、Achernar、Gacrux、Pulcherrima、Vindemiatrix、Sulafat、Puck、Charon、Fenrir、Orus、Enceladus、Iapetus、Umbriel、Algieba、Algenib、Rasalgethi、Alnilam、Schedar、Achird、Zubenelgenubi、Sadachbia、Sadaltager。默认 Kore。
- **ElevenLabs 52 个：** Rachel、Sarah、Aria、Laura、Alice、Matilda、Jessica、Lily、Domi、Elli、Emily、Charlotte、Dorothy、Freya、Gigi、Grace、Nicole、Serena、Glinda、Mimi、Adam、Antoni、Josh、Arnold、Sam、Roger、Charlie、George、Callum、Harry、Liam、Will、Eric、Chris、Brian、Daniel、Bill、River、Drew、Clyde、Paul、Dave、Fin、Thomas、Patrick、James、Joseph、Jeremy、Michael、Ethan、Jessie、Giovanni。默认 Rachel。官方预置音色计划在 2026-12-31 后停用。
- **CosyVoice 88 个：** 龙安洋、龙安欢（V3）、龙安欢、龙呼呼、龙泡泡、龙杰力豆、龙仙、龙铃、龙闪闪、龙牛牛、龙嘉欣、龙嘉怡、龙安粤、龙老铁、龙陕哥、龙安闽、loongkyong、Riko、loongtomoka、loongabby、loongandy、loongannie、loongava、loongbeth、loongbetty、loongcally、loongcindy、loongdavid、loongdonna、loongemily、loongeric、loongluna、loongluca、loongtomoya、Yuuna、Yuuma、Jihun、loongindah、龙飞、龙应笑、龙应询、龙应静、龙应聆、龙应桃、龙小淳、龙小夏、YUMI、龙安昀、龙安温、龙安莉、龙安朗、龙应沐、龙安台、龙华、龙橙、龙泽、龙哲、龙颜、龙星、龙天、龙婉、龙嫱、龙菲菲、龙浩、龙安柔、龙寒、龙安智、龙安灵、龙安雅、龙安亲、龙妙、龙三叔、龙媛、龙悦、龙修、龙楠、龙婉君、龙逸尘、龙老伯、龙老姨、龙机器、龙猴哥、龙黛玉、龙安燃、龙安宣、龙硕、龙书、Bella3.0。
- **豆包合成 100 个：** Vivi、小何、云舟、小天、刘飞、魅力苏菲、清新女声、知性灿灿、撒娇学妹、甜美小源、甜美桃子、爽快思思、佩奇猪、邻家女孩、少年梓辛、猴哥、Tina老师、暖阳女声、儿童绘本、大壹、黑猫侦探社咪仔、鸡汤女、魅力女友、流畅女声、儒雅逸辰、Tim、Dacey、Stokie、温柔妈妈、解说小明、TVB女声、译制片男、俏皮女声、直率英子、邻家男孩、四郎、儒雅青年、擎苍、熊二、樱桃丸子、温暖阿虎、奶气萌娃、婆婆、高冷御姐、傲娇霸总、懒音绵宝、反卷青年、温柔淑女、古风少御、活力小哥、霸气青叔、悬疑解说、萌丫头、贴心女声、鸡汤妹妹、磁性解说男声、亮嗓萌仔、开朗姐姐、高冷沉稳、深夜播客、鲁班七号、娇喘女声、林潇、玲玲姐姐、春日部姐姐、唐僧、庄周、开朗弟弟、猪八戒、感冒电音姐姐、谄媚女声、女雷神、亲切女声、快乐小东、开朗学长、悠悠君子、文静毛毛、知性女声、清爽男大、渊博小叔、阳光青年、清澈梓梓、甜美悦悦、心灵鸡汤、温柔小哥、柔美女友、东方浩然、温柔小雅、天才童声、武则天、顾姐、广告解说、少儿故事、Charlie、Ethan、Alastor、Chucky、Noah、Jigsaw、Clown Man。中文默认 Vivi，英语默认 Dacey，日语和韩语各有默认女声。

此外，TTS 支持流式合成与播放、按句切分、排队或打断、同步字幕、角色单独绑定音色，以及按对话语言记住默认音色。

## 5. 全双工语音交互

- 边说边听。
- 五种插话和排队策略。
- 短附和不一定打断，新问题可以打断。
- 跳舞时说「跳得真好」不打断，说「换一支」才切换。
- Silero VAD 语音活动检测。
- WebRTC AEC3 回声消除。
- 欢迎语、沉默续聊、主动搭话、告别。
- 会话时长到达后自动告别。
- 各项等待时间可配置。

## 6. 长期记忆

- mem0 提取长期事实。
- 本地 SQLite 保存原文，Qdrant 保存向量索引。
- 记录偏好、人物关系、约定、情绪事件和会话摘要。
- 钉住重要原句并单独注入。
- 记忆可查看、删除。
- 角色扮演内容默认不进入长期记忆。
- **6 种向量选择**：自动、本地 MiniLM、豆包、通义、OpenAI、Gemini。
- 更换向量服务后后台重建索引。
- 低配置设备可自动关闭记忆，避免资源占用。

## 7. 2D / 3D 舞台与表演

- 支持 **PMX（MMD）、VRM、GLB**。
- 可选独立 **Live2D** 模块，默认关闭；支持完整 ZIP 模型包、热切换、模型动作与物理、口型、眨眼、情绪和待机。Live2D 不支持 VMD、3D 运镜和全身骨骼动捕。
- 统一意图动作映射：Live2D 调用 `motion3.json` 动作组，GLB 通过 `AnimationMixer` 播放内嵌动画；缺少对应动作时回退到头部或骨骼程序化动作，PMX 仍使用过审 VMD。
- Live2D 高级互动：平滑视线与头部跟随、拖拽缩放、部位触碰、原生动作中心、组合换装与眼镜互斥、参数搜索与捏脸滑杆、单项/全部复位；装扮、参数、视线和视图按模型本地持久化。
- 模型能力清单自动驱动 UI 与 LLM：读取动作组、表情、参数范围和用户预设，不针对具体模型硬编码；支持 `[motion:]`、`[outfit:]`、`[param:]`、`[preset:]` 标签，拒绝不存在的资源和越界参数。
- 模型热切换。
- MMD 布料和刚体物理。
- 表情、口型、动作、舞蹈、站位和运镜联动。
- `[emo:]`、`[act:]`、`[intent:]`、`[dance:]`、`[cam:]`、`[stand:]` 表演标签。
- 自动眨眼、呼吸、待机、聆听、思考和说话状态。
- VMD 舞蹈及 BGM。
- 镜头组合审查，减少穿模和动作错位。
- 六档景别。
- 物理开关、渲染分辨率、灯光、音量设置。
- 20 个图片背景、6 个纯色背景、自定义背景。
- 舞台底座贴图、颜色、发光和透明度设置。

## 8. 动捕与互动

- 摄像头实时动捕。
- 本地 MP4/WebM 视频动捕，便于重复测试。
- MediaPipe Holistic 检测身体、双手和面部。
- PMX 完整骨骼驱动，VRM/GLB 人体骨骼映射。
- 身体区域触碰反馈。
- 舞台和桌宠共用触碰逻辑。
- 拖拽桌宠不会被误判为触碰。

## 9. 透明桌宠

- 置顶透明窗口。
- 空白区域点击穿透。
- 拖动角色移动、拖动边角缩放。
- 记住位置、大小、显示器和当前角色。
- 多显示器及断屏后的可见区域恢复。
- 空闲时自主走动，对话和拖动时停下。
- 头顶对话气泡和麦克风。
- 最小化、重载、关闭、返回完整舞台。

## 10. 一起看与屏幕理解

- 默认关闭。
- 单次查看屏幕和持续陪看分开。
- 本地 **MiniCPM-V 4.7 1B** 视觉进程。
- 也可配置其他 OpenAI 兼容视觉模型。
- 连续滑动视频窗口和真实时间戳。
- 陪看电影、短视频、听音乐。
- 游戏画面理解，可结合英雄联盟客户端状态和本地 OCR。
- 字幕时间轴、场景策略和语言感知。
- 画面和声音留在本机，对话只接收短文本摘要。
- 不点击、不操作电脑。
- 停止陪看或退出应用时关闭视觉进程。
- 本地陪看记录及近期截图管理。
- **MiniCPM-o 4.5 Omni 测试接口**：文字、语音、图片输入，支持面壁云端或自建 Gateway。

## 11. 陪伴玩法

- **9 种塔罗牌阵**。
- 80 张原创国风牌面。
- 代码控制发牌和正逆位。
- 语音抽牌、补牌、换牌和重新开局。
- **22 张情境卡**，也可根据记忆生成情境。
- 证物相册：截图、约 8 秒短片、按角色归档。
- 证物可临时作为舞台背景。
- 重说、历史回溯、换情绪再演。
- 会话记录和后端对话日志。

## 12. 魅影酒馆

- 四人诈牌对局。
- 三名模型驱动的 AI 对手。
- 跟牌、揭穿、三膛左轮和计分。
- 四套牌面美术。
- 电影化裁决。
- 角色语音演出。
- 说话时不冻结牌桌。
- 可为牌桌角色分配不同语音。

## 13. 游戏、编程与直播

- 自然语言打开 WeGame、Steam、Epic 已安装游戏。
- 检查本地游戏库和启动后的进程。
- 游戏不存在时只打开平台，不自动安装。
- Code 伴侣支持：
  - Cursor
  - Codex
  - Claude Code
  - 通义灵码
  - Trae
  - 文心快码
- 识别开工、进行中、完成和空闲状态。
- 抖音、B 站弹幕、关注和礼物接入。
- 消息聚合、重连去重、队列容量和时效控制。
- 真实播放回执及未完成礼物回应补播。
- 本地直播彩排实验室：虚构观众、替身模型、故障注入和持久收据。

## 14. 绘图、联网与金币

- 火山 Seedream 绘图。
- 图片展示、放大和自动进入证物相册。
- 查询天气、股价、金价、汇率、新闻和比分。
- 本机金币账本，不登录、不上传。
- 在线时长和聊天 Token 产生金币。
- 许愿池每天 50 次。
- 三件随机道具、金币雨和语音旁白。
- 地址签名转账、导入转账单和销毁。

## 15. 资产、语言和系统设置

- ZIP、RAR、单文件导入。
- 自动解压、乱码文件名修复和资产分类。
- VPD 姿势转 VMD。
- 模之屋搜索和下载。
- A/B 内容包识别。
- 简体中文、英语、日语、韩语。
- 界面语言和对话语言独立。
- 对话语言可固定或跟随用户当前句子。
- 记忆、情境、重说、证物、塔罗、魅影酒馆、Code 伴侣、触碰、Harness、直播等模块独立开关。
- 自定义应用 Logo 和配色。
- Windows A/B 体验包，自带 Chromium 和 Python 运行时。
- 源码开发、Windows 打包和本地部署。

## 附属项目

- `companion-3d/`：早期独立 3D 渲染和动作原型。
- `music-api/`：独立音乐检索研究接口。

以上附属项目不属于 `companion/` 主产品的核心功能。
