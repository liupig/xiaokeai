# 多语言改造方案

把小可爱从「只服务中文环境和中文对话」改成可切换语言的本地陪玩。第一刀做通 **简体中文 + 英文**。日语、韩语走同一套语言包，不另起架构。

本文只改语言。Windows 安装包、Mac、手机不在这次范围里。模之屋仍是中文素材站，海外用户用本地导入 VRM / PMX / GLB。

## 结论

语言锁在四层，不是界面文案一层：

| 层 | 现在 | 不改的后果 |
|---|---|---|
| 界面 | Vue 文案写死中文，Naive UI 锁 `zhCN`，没有 i18n | 英文用户打不开设置 |
| 对话 | 系统协议、人设、记忆抽取、双工提示、塔罗口吻都要求「用中文说」 | 换成 GPT 也会被拉回中文 |
| 口令 | 扮演进出、塔罗仪式、打断、换舞是中文正则，前后端各写一份 | 说 stop / draw a card 没反应 |
| 语音 | 浏览器识别和朗读锁 `zh-CN`；在线音色只有中文 Neural；分句按汉字和结巴 | 英文句子被切碎，音色和文字对不上 |

表演标记本身已经是语言无关的：`[emo:happy]` `[intent:greet]` `[cam:half]` `[stand:left]` `[dance:文件名]`。这层保持英文键，不翻译。

口型跟音频振幅走，不依赖中文音素。换语言不用重做口型引擎。

本地记忆向量已经是 `paraphrase-multilingual-MiniLM-L12-v2`，中英可以进同一个库。要改的是抽取提示和「用户的名字是…」这类中文句式。

离线 SenseVoice 已是 `language="auto"`（中/英/日/韩/粤）。浏览器 Web Speech 仍锁死 `zh-CN`。

## 目标体验

设置里两个开关，互不绑架：

- **界面语言**：按钮、设置、报错、空状态。
- **对话语言**：她怎么说、语音识别、音色、记忆怎么记、口令认哪种话。

默认跟系统语言，认不出就 `zh-CN`。已有用户不改设置时，行为与现在一致。

对话语言可选「固定」或「跟着我这句」。跟着这句话时，只在整句明显是另一种文字时才切（一整句英文才切英文）。一句里夹一两个英文单词，保持当前对话语言。中英夹杂是中文用户的常态，不能见一个拉丁词就切走。

她说的话、屏幕字幕、入库记忆，使用同一对话语言。

## 语言包

新增目录 `companion/locales/`，一种语言一个文件夹。前后端读同一份，塔罗和扮演的正则不再各写一遍。

```
companion/locales/
  zh-CN/
    ui.json           # 界面
    prompts.yaml      # 导演手册、双工、记忆抽取、Code 伴侣、全模态
    intents.yaml      # 扮演进出、打断、塔罗仪式
    content.yaml      # 情境卡、塔罗牌名与讲法、内置人设、垫话
  en/
    （同结构）
```

语言代码用 BCP 47：`zh-CN`、`en`、`ja`、`ko`。

设置增加字段，写进现有 JSON 设置（`settings_store.py` / `stores/settings.ts`）：

```json
{
  "locale": {
    "ui": "zh-CN",
    "reply": "en",
    "reply_mode": "fixed"
  }
}
```

`reply_mode`：`fixed` 或 `follow`。

每次组 prompt、做语音识别、选音色、抽记忆，都带上当前 `reply`。界面只读 `ui`。

缺包的玩法不要用中文硬顶。塔罗、情境在该语言的 `content.yaml` 没有之前，设置里该项标成「此语言暂无」，模块可关。聊天、表情、动作、本地导入模型必须先可用。

## 什么不要翻译

- 表演标记的键和取值：`emo` / `intent` / `cam` / `stand`。
- 动作文件名、模型文件名、镜头审查的内部 id。
- 代码注释、日志、文档。文档可以后补英文 README，不阻塞产品。
- 已入库的旧记忆。中文事实继续以中文躺在库里，新抽取跟随对话语言。不做翻译迁移。
- 「清宵」这个人设。她是中文角色，不机翻成英文脸。英文首发用通用人设模板另写一版，或让用户自己写人设。

## 分四期

### 一期：英文能聊完一轮

做完就叫「全世界能对话」。界面可以仍是中文。

验收：

1. 对话语言切到 English。她用短口语英文回，不夹中文，不念标记。
2. 浏览器识别 `en-US`，Qwen 英文音色（Ryan / Aiden）或 edge 英文音色读英文。
3. 说 stop、be a teacher、stop roleplay、another dance，能打断、进扮演、出扮演、换舞。
4. 新记忆是英文短句。切回中文后，旧的中文聊天和中文口令与现在一致。
5. 一句超过二十个汉字的长度假设不再把英文切成两三个词一片。

### 二期：界面

验收：界面语言切 English 后，顶栏、对话栏、设置、资产中心、角色卡、报错、空舞台提示为英文。Naive UI 组件（日期、分页、空状态）跟着切。切回中文无残句。

### 三期：玩法内容

验收：英文下能点开塔罗走完日抽（切牌、翻牌、她用英文讲、说收起来能收摊）。情境卡有英文标题和开场。Code 伴侣开工/收工是英文短句。没有内容包的语言不显示这些入口。

### 四期：第三种语言验包

用日语走同一目录再装一包（Qwen 已有小野安娜）。验的是「加语言只加文件夹」，不再改分句、设置和 prompt 架子。韩语同理（素熙）。

## 逐项改什么

### 1. 对话协议（一期，最高优先级）

这些字符串决定她说哪种语言。各做一份 `prompts.yaml`，组装时按 `reply` 取。

| 位置 | 内容 |
|---|---|
| `backend/app/services/llm.py` | `SYSTEM_PROTOCOL` 第 1 条「用口语化中文回复」；例子全是中文 |
| `backend/app/services/prompt_stack.py` | 扮演进出模板、`FALLBACK_PERSONA`、时间槽文案；`_EXIT_RE` / `_ENTER_RE` 改读 `intents.yaml` |
| `backend/app/services/duplex.py` | 续聊、主动搭话、告别、欢迎、塔罗收束提示；垫话 `嗯… / 我看看… / 稍等…` |
| `backend/app/modules/memory/service.py` | `_EXTRACT_HINT`、姓名句式 `用户的名字是` |
| `backend/app/modules/codewatch/speak.py` | 开工/收工提示和字数上限 |
| `backend/app/services/omni_minicpm.py`、`routers/omni.py` | 默认「用中文介绍你自己」 |
| `frontend/src/features/settings/SettingsPanel.vue` | 全模态试听占位句，跟随对话语言 |

协议正文用目标语言写，避免「用英文解释中文规则」让模型串味。标记列表保持现在的英文键。

字数上限按语言分：中文「最多 16 个字」，英文「最多 12 个词」。不要把「16 个字」直接译成 16 words。

`prompt_stack.py` 里的扮演正则是安全边界（越狱句、高危身份）。英文包要有对应说法（ignore your rules、you are a doctor、stop roleplay），不能只留中文正则。

### 2. 口令（一期）

同一意图，前后端现在各有一份中文正则，容易改漏。收到 `intents.yaml` 后两边加载。

| 意图 | 前端 | 后端 |
|---|---|---|
| 塔罗唤醒、切牌、翻牌、换牌、收摊 | `frontend/src/features/tarot/intent.ts` | `backend/app/modules/tarot/service.py` |
| 说话中打断、换舞、过来、坐下 | `frontend/src/features/voice/ingress.ts` 的 `CUT_RE` | 与导演口令对齐的部分 |

英文包至少覆盖：draw a card、three cards、yes or no、cut、you pick、flip、stop、put the cards away、another dance、come here、sit down、be a …、stop roleplay。

按钮和菜单照常可用，不依赖口令。口令是语音用户的入口。

### 3. 分句与语音（一期）

| 位置 | 改法 |
|---|---|
| `backend/app/services/speech_split.py` | 中文：现行标点 + 结巴 + 约 20 字。英文：按 `.?!` 和逗号切，长度按词（大约 12–18 词一句）。日文按 `。！？` |
| `frontend/src/features/voice/speechSplit.ts` | 与后端同一套规则。前端无结巴，英文路径本来就不需要结巴 |
| `frontend/src/features/voice/stt.ts` | `rec.lang = 'zh-CN'` 改为对话语言的 BCP 47（`en-US`、`ja-JP`、`ko-KR`） |
| `frontend/src/features/voice/tts.ts` | `utter.lang` 同样跟随；浏览器语音选该语言的 voice |
| `backend/app/services/tts.py` | edge 音色按语言列清单。现在只有 `zh-CN-*` |
| `backend/app/services/tts_qwen.py` | 已有中/英/日/韩声线。对话语言一切换，若当前音色语言不符，落到该语言的默认音色 |
| `backend/app/services/asr.py` | SenseVoice 保持 `auto`。状态文案随界面语言 |
| `backend/app/services/autotune.py` | 试听句和 `EDGE_VOICE` 跟随对话语言 |

音色和对话语言绑定。用中文声线读英文句子不算做完。

### 4. 界面（二期）

前端没有 vue-i18n。Vue 3.4 使用 vue-i18n 9。文案进 `locales/*/ui.json`，键用路径，例如 `settings.voice.engine`。

`App.vue` 里 Naive UI 的 `zhCN` / `dateZhCN` 按界面语言换成 `enUS` 等。

中文出现最多、要先抽完的界面：

- `features/settings/SettingsPanel.vue`
- `features/chat/ChatBar.vue`、`stores/chat.ts`（本地兜底回复也在这里）
- `features/assets/AssetCenter.vue`
- `features/character/CharacterPanel.vue`
- `features/review/CamReviewPanel.vue`
- `features/hud/QuickPanel.vue`、`LiveBeatHud.vue`
- `features/tarot/Dock.vue`、`features/codewatch/Dock.vue`
- `features/memory/MemoryPanel.vue`、`features/keepsake/KeepsakeGallery.vue`

`features/performance/lexicon.ts` 里的中文是给选角和审查界面看的说明。机器仍用 `Intent` 英文枚举。说明进 `ui.json`，枚举不动。

`localeCompare(..., 'zh')`（`camReview.ts`）改为当前界面语言。

服务商预设的显示名进 `ui.json`。接口地址和模型 id 不动。默认对话模型仍是豆包；英文界面里把 OpenAI / Gemini 放在预设列表前面即可，不必按地区偷偷改用户已保存的 key。

### 5. 玩法内容（三期）

这是内容工程，不是把字符串抽出去。

**塔罗。** `modules/tarot/lore.py`（牌面与正逆）、`reader.py`（讲法口吻和「玉币不要说星币」这类专名）、`plays.py`、`deck.py` 全是中文文学稿。牌图可以继续用现在的国风图。英文包另写：

- 口头牌名用通行英文（The Fool、Wands、Cups、Swords、Pentacles），不要把「玉币 / 竹杖 / 瓷盏 / 古剑」直译后再禁止说 Wands。
- 讲法保持现在的味道：先报位置和牌名，再讲画面，不讲算命。英文重写例句，不机翻。
- 中文包继续用玉币、竹杖、瓷盏、古剑。两套专名不要混进同一次解读。

**情境。** `frontend/src/features/scenes/catalog.ts` 与 `backend/app/modules/scenes/catalog.py` 双份中文。收成 `content.yaml` 的场景列表，两边读取，避免再漂移。

**人设。** `frontend/src/features/character/personas.ts` 与 `backend/app/personas.py` 是中文模板。通用模板按语言各一份。清宵只留在 `zh-CN`。

**动作中文标签。** `backend/app/services/catalog.py` 的内置标签进语言包。用户导入的文件名保持原样，没有译文就显示文件名。

### 6. 记忆（一期就改抽取，三期再看展示）

抽取提示改为「用 {对话语言} 写短句」。姓名句式按语言匹配，例如英文 `The user's name is X`，中文仍是 `用户的名字是X`。

向量模型不用换。记忆面板的栏名走界面语言；记忆正文显示原句，不翻译。

扮演期间不入库的规则保持，与语言无关。

## 建议的默认值

| 项 | 值 |
|---|---|
| 首发语言 | `zh-CN`、`en` |
| 老用户缺字段 | `ui=zh-CN`，`reply=zh-CN`，`reply_mode=fixed` |
| 新装、系统是英文 | `ui=en`，`reply=en` |
| 英文默认识别 | 浏览器 `en-US`；离线仍 SenseVoice auto |
| 英文默认音色 | 有 NVIDIA 用 Qwen Ryan；否则 edge 英文女声 |
| 无内容包的模块 | 隐藏入口，聊天不受影响 |

## 验收清单

一期合并前：

- 中文默认路径回归：塔罗日抽、换舞、扮演进出、打断、记忆抽取，与改前一致。
- 英文路径：连续十轮不出现中文句子和中文标点式垫话；stop / another dance / be a teacher / stop roleplay 可用。
- 来回切换语言：音色跟着换，旧聊天记录不改写。
- 分句：英文一长句不会按 20 个字符硬切。

二期：设置页从模型、语音、模块到资源包，英文下没有中文按钮。

三期：英文塔罗一场读完，牌名不出现玉币/竹杖；中文塔罗仍禁止说成星币/权杖。

## 风险

- **正则双份。** 塔罗口令现在前端 `intent.ts` 和后端 `service.py` 各一份。收成一份 `intents.yaml` 是一期的一部分，否则英文会只通一边。
- **文学稿机翻。** 塔罗和清宵机翻会毁掉产品味道。英文塔罗和英文人设要重写，不进一期。
- **字数规则。** 双工和 Code 伴侣的「N 个字」若原样留在英文提示里，她会说得很短或很怪。
- **夹杂切换。** 「跟着我这句」若按单个英文词触发，中文会话会被 API、VRM、stop 打散。只认整句文字。
- **音色空档。** 某语言没有离线音色时，自动落到该语言的 edge 在线音色，并在语音设置里写明。不要用晓伊读英文。
