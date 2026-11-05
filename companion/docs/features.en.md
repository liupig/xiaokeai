# xiaoke.ai Complete Feature List

[简体中文](./features.md) · **English** · [Back to README](../../README.md)

This document is based on the current code and existing feature documentation. It covers implemented capabilities only, not TODO items, plans, or features explicitly excluded. The README provides a product overview; this document is the complete checklist for reviewing the project's scope.

## 1. AI Chat and Model Providers

- **38 chat-service presets**, plus custom OpenAI-compatible endpoints.
- OpenAI, Anthropic, Gemini, DeepSeek, Qwen, Doubao, Kimi, Zhipu, MiniMax, OpenRouter, and other providers.
- Local model servers: **Ollama, vLLM, SGLang, and Player2**.
- Streaming replies, connection testing, thinking mode, temperature, `top_p`, and reply-length settings.
- Local fallback replies without an API key, with the stage and performance pipeline still available.
- Built-in **DeepSeek Harness (dsh)** chat agent.
- Harness skills for chat, dance, tarot, drawing, web lookup, visual companionship, and game launching.
- Shared character sessions, history reconstruction, context budgets, and session rotation.

### 38 Chat-Service Presets

Select a provider under **Settings → AI chat** to fill in its endpoint and recommended model automatically. You still need your own key for that provider; keys remain on the local computer and are not written to the database. When a key field is empty, a system environment variable or local `.env` value can be used. You can also skip the presets, enter a custom endpoint and model, and use **Test connection**.

Services such as Azure and Cloudflare, whose endpoints contain user-specific resource names, use the custom compatible-endpoint option rather than dedicated presets.

| # | Provider | Recommended model |
|---:|---|---|
| 1 | Alibaba Cloud Model Studio (Qwen / Kimi) | `qwen-plus` |
| 2 | Qwen International | `qwen-plus` |
| 3 | Volcengine Ark (Doubao) | `doubao-seed-1-6-250615` |
| 4 | Volcengine Ark (Doubao Character) | `doubao-seed-character-260628` |
| 5 | ModelBest MiniCPM-o 4.5 Omni | `MiniCPM-O-4.5-9B` |
| 6 | DeepSeek | `deepseek-chat` |
| 7 | Moonshot (Kimi) | `kimi-k2-turbo-preview` |
| 8 | Moonshot International | `kimi-k2-turbo-preview` |
| 9 | Zhipu GLM | `glm-4.5-flash` |
| 10 | SiliconFlow | `deepseek-ai/DeepSeek-V3` |
| 11 | StepFun | `step-2-mini` |
| 12 | Baichuan | `Baichuan4-Turbo` |
| 13 | MiniMax | `MiniMax-M2` |
| 14 | ModelScope | `Qwen/Qwen2.5-72B-Instruct` |
| 15 | Tencent Hunyuan | `hunyuan-turbos-latest` |
| 16 | Xiaomi MiMo Flash | `mimo-v2.6-flash` |
| 17 | Xiaomi MiMo Pro | `mimo-v2.6-pro` |
| 18 | AIHubMix | `gpt-4o-mini` |
| 19 | 302.AI | `gpt-4o-mini` |
| 20 | OpenAI | `gpt-4o-mini` |
| 21 | Anthropic Claude | `claude-sonnet-4-5`, using the compatible endpoint and Anthropic headers |
| 22 | Google Gemini (OpenAI-compatible) | `gemini-2.0-flash` |
| 23 | OpenRouter | `openai/gpt-4o-mini` |
| 24 | Groq | `llama-3.3-70b-versatile` |
| 25 | Mistral | `mistral-small-latest` |
| 26 | xAI (Grok) | `grok-3` |
| 27 | Together.ai | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| 28 | Fireworks.ai | `accounts/fireworks/models/llama-v3p3-70b-instruct` |
| 29 | NVIDIA NIM | `meta/llama-3.3-70b-instruct` |
| 30 | Cerebras | `llama-3.3-70b` |
| 31 | Perplexity | `sonar` |
| 32 | Novita | `deepseek/deepseek-v3` |
| 33 | CometAPI | `gpt-4o-mini` |
| 34 | Featherless | `meta-llama/Llama-3.3-70B-Instruct` |
| 35 | Ollama, local `127.0.0.1:11434` | `llama3.2`; run Ollama yourself; it is not bundled |
| 36 | vLLM, local `127.0.0.1:8000` | `default` |
| 37 | SGLang, local `127.0.0.1:30000` | `default` |
| 38 | Player2, local `127.0.0.1:4315` | `player2` |

Chat parameters:

| Parameter | Range | Purpose |
|---|---|---|
| Thinking mode | Model default / forced on / forced off | Reasons before answering and may slow the first sentence; use the default for unsupported models |
| Temperature | 0–1.5, step 0.05 | Controls response variation |
| `top_p` | 0.1–1, step 0.05 | Controls sampling |
| Reply-length limit | 0–32768, step 256 | 0 uses the provider default |

Replies stream incrementally. Performance tags are stripped from the text and are not spoken.

## 2. Personas, Character Cards, and Lorebooks

- Layered persona stack: identity, temporary role-play, time, time apart, memory, scene, performance directions, and boundaries.
- Temporary roles can be entered and exited without changing the long-term persona.
- **27 Chinese persona templates**.
- Five conversation-boundary levels, from all-ages to unrestricted character-driven role-play.
- Per-character settings for:
  - Bound model
  - Persona and greeting
  - Alternate greetings
  - Voice
  - Emotion-to-morph mapping
  - Idle-motion preferences
  - Tags and creator information
- **SillyTavern v1/v2/v3 PNG/JSON character-card import**.
- **AICC character-card import**.
- **SillyTavern V2 PNG character-card export**.
- Preservation of unknown source-card fields, creator metadata, and extensions.
- Lorebook support:
  - Keyword and regular-expression triggers
  - Constant entries
  - Selective entries
  - Injection order and position
  - Bounded recursive triggering
  - Injection-size limits
- Optional user persona without rewriting the character.

Character-card formats and the Lorebook concept come from the open [SillyTavern](https://github.com/SillyTavern/SillyTavern) ecosystem and community character-card specifications. xiaoke.ai provides compatible import, layered-prompt integration, and 3D-stage presentation. Card authors retain their copyrights.

## 3. Speech Recognition — ASR

**7 options.** Recognition and synthesis engines are configured independently. Except for browser Web Speech, Silero VAD in the browser detects speech boundaries and sends each recorded segment for recognition.

| # | Engine | Runs | Model, credentials, and notes |
|---:|---|---|---|
| 1 | SenseVoice-Small | **Offline, local CPU** | Automatic Chinese, English, Japanese, Korean, and Cantonese; approximately 230 MB downloaded by **Prepare / Download model**; separate process from TTS |
| 2 | Alibaba Cloud Model Studio | Cloud | `qwen3-asr-flash`; shares the Model Studio `sk-` key with chat |
| 3 | Volcengine Doubao ASR 2.0 | Cloud | `volc.seedasr.sauc.duration`; can share the Ark key, or use `VOLC_SPEECH_API_KEY` if speech authentication fails |
| 4 | OpenAI | Cloud | `gpt-transcribe`; can share the chat key or use `OPENAI_API_KEY`; the endpoint must point to OpenAI |
| 5 | ElevenLabs | Cloud | `scribe_v2`; uses `ELEVENLABS_API_KEY` for both ASR and TTS; no chat or embedding service |
| 6 | Google Gemini | Cloud | `gemini-2.5-flash` audio understanding; can share the chat key or use `GEMINI_API_KEY` |
| 7 | Browser Web Speech | Cloud / browser | Chrome and Edge; default recognition method |

WebRTC AEC3 cancels the companion's playback. When VAD detects speech while audio is playing, frames that resemble echo are not treated as the user interrupting.

## 4. Speech Synthesis — TTS

**9 options, plus off**, with **300+ listed preset voices** in total. Lip-sync follows real audio amplitude rather than language-specific phonemes; browser system speech does not provide true lip-sync. Changing the conversation language selects the voice remembered for that language, while changing only the interface language leaves the voice unchanged.

| # | Engine | Runs | Model / voices |
|---:|---|---|---|
| 1 | Qwen3-TTS | **Offline, local GPU, streaming PCM** | 0.6B or 1.7B with 9 shared voices; NVIDIA GPU recommended |
| 2 | Browser system speech | Local | Voices installed on the device; no true lip-sync |
| 3 | Xiaomi MiMo | Cloud, 24 kHz PCM16 streaming | `mimo-v2.5-tts`; 9 preset voices with emotion and free-text directions |
| 4 | Volcengine Doubao TTS 2.0 | Cloud | `seed-tts-2.0`; 100 voices |
| 5 | Alibaba Cloud CosyVoice | Cloud, streaming | CosyVoice-v3-Flash; 88 Long/loong-series voices |
| 6 | OpenAI TTS | Cloud | `gpt-4o-mini-tts`; 13 voices, Marin by default |
| 7 | ElevenLabs | Cloud, streaming | Flash v2.5; 52 official presets, excluding user-cloned voices |
| 8 | Google Gemini TTS | Cloud, streaming PCM | `gemini-3.8-flash-lite-tts`; 30 voices, Kore by default |
| 9 | edge-tts | Cloud, streaming | Microsoft neural voices; 11 built-in choices |
| 10 | Speech off | — | Text only, no spoken audio |

### Local Qwen3-TTS Specifications

- **0.6B:** faster and uses less GPU memory.
- **1.7B:** higher quality, approximately 4 GB of weights, with default, cool mature, husky, gentle/flirtatious, and custom style instructions.
- Switching model sizes unloads the old model before loading the new one.
- Recommended combination for Qingxiao: 1.7B + Serena + cool mature style.
- Use edge-tts when a suitable NVIDIA GPU is unavailable.

### Preset Voice Names

- **Qwen — 9:** Vivian (bright young woman), Serena (gentle woman), Uncle_Fu (steady man), Dylan (Beijing man), Eric (Chengdu man), Ryan (English man), Aiden (American man), Ono Anna (Japanese woman), and Sohee (Korean woman). Serena is the Chinese and English default, Ono Anna the Japanese default, and Sohee the Korean default.
- **MiMo — 9:** 冰糖, 茉莉, 苏打, 白桦, `mimo_default` (冰糖 on the China cluster), Mia, Chloe, Milo, and Dean.
- **edge-tts — 11:** 晓伊 (lively young woman), 晓晓 (gentle woman), 云希 (young man), 云健 (adult man), 晓北 (Northeastern Mandarin), 晓臻 (Taiwanese Mandarin), Aria, Jenny, Guy, 七海 (Japanese), and SunHi (Korean).
- **OpenAI — 13:** Marin, Cedar (officially recommended), Alloy, Ash, Ballad, Coral, Echo, Fable, Nova, Onyx, Sage, Shimmer, and Verse.
- **Gemini — 30:** Kore, Zephyr, Leda, Aoede, Callirrhoe, Autonoe, Despina, Erinome, Laomedeia, Achernar, Gacrux, Pulcherrima, Vindemiatrix, Sulafat, Puck, Charon, Fenrir, Orus, Enceladus, Iapetus, Umbriel, Algieba, Algenib, Rasalgethi, Alnilam, Schedar, Achird, Zubenelgenubi, Sadachbia, and Sadaltager. Kore is the default.
- **ElevenLabs — 52:** Rachel, Sarah, Aria, Laura, Alice, Matilda, Jessica, Lily, Domi, Elli, Emily, Charlotte, Dorothy, Freya, Gigi, Grace, Nicole, Serena, Glinda, Mimi, Adam, Antoni, Josh, Arnold, Sam, Roger, Charlie, George, Callum, Harry, Liam, Will, Eric, Chris, Brian, Daniel, Bill, River, Drew, Clyde, Paul, Dave, Fin, Thomas, Patrick, James, Joseph, Jeremy, Michael, Ethan, Jessie, and Giovanni. Rachel is the default. These official presets are scheduled for retirement after 2026-12-31.
- **CosyVoice — 88:** 龙安洋、龙安欢（V3）、龙安欢、龙呼呼、龙泡泡、龙杰力豆、龙仙、龙铃、龙闪闪、龙牛牛、龙嘉欣、龙嘉怡、龙安粤、龙老铁、龙陕哥、龙安闽、loongkyong、Riko、loongtomoka、loongabby、loongandy、loongannie、loongava、loongbeth、loongbetty、loongcally、loongcindy、loongdavid、loongdonna、loongemily、loongeric、loongluna、loongluca、loongtomoya、Yuuna、Yuuma、Jihun、loongindah、龙飞、龙应笑、龙应询、龙应静、龙应聆、龙应桃、龙小淳、龙小夏、YUMI、龙安昀、龙安温、龙安莉、龙安朗、龙应沐、龙安台、龙华、龙橙、龙泽、龙哲、龙颜、龙星、龙天、龙婉、龙嫱、龙菲菲、龙浩、龙安柔、龙寒、龙安智、龙安灵、龙安雅、龙安亲、龙妙、龙三叔、龙媛、龙悦、龙修、龙楠、龙婉君、龙逸尘、龙老伯、龙老姨、龙机器、龙猴哥、龙黛玉、龙安燃、龙安宣、龙硕、龙书、Bella3.0。
- **Doubao TTS — 100:** Vivi、小何、云舟、小天、刘飞、魅力苏菲、清新女声、知性灿灿、撒娇学妹、甜美小源、甜美桃子、爽快思思、佩奇猪、邻家女孩、少年梓辛、猴哥、Tina老师、暖阳女声、儿童绘本、大壹、黑猫侦探社咪仔、鸡汤女、魅力女友、流畅女声、儒雅逸辰、Tim、Dacey、Stokie、温柔妈妈、解说小明、TVB女声、译制片男、俏皮女声、直率英子、邻家男孩、四郎、儒雅青年、擎苍、熊二、樱桃丸子、温暖阿虎、奶气萌娃、婆婆、高冷御姐、傲娇霸总、懒音绵宝、反卷青年、温柔淑女、古风少御、活力小哥、霸气青叔、悬疑解说、萌丫头、贴心女声、鸡汤妹妹、磁性解说男声、亮嗓萌仔、开朗姐姐、高冷沉稳、深夜播客、鲁班七号、娇喘女声、林潇、玲玲姐姐、春日部姐姐、唐僧、庄周、开朗弟弟、猪八戒、感冒电音姐姐、谄媚女声、女雷神、亲切女声、快乐小东、开朗学长、悠悠君子、文静毛毛、知性女声、清爽男大、渊博小叔、阳光青年、清澈梓梓、甜美悦悦、心灵鸡汤、温柔小哥、柔美女友、东方浩然、温柔小雅、天才童声、武则天、顾姐、广告解说、少儿故事、Charlie、Ethan、Alastor、Chucky、Noah、Jigsaw、Clown Man。Chinese defaults to Vivi, English to Dacey, and Japanese and Korean have their own default female voices.

TTS also supports streaming synthesis and playback, sentence segmentation, queueing or interruption, synchronized captions, per-character voice binding, and a remembered default voice for each conversation language.

## 5. Full-Duplex Voice Interaction

- Listen while speaking.
- Five interruption and queueing strategies.
- Short acknowledgements need not interrupt, while new questions can.
- “That was a great dance” does not stop a dance, while “change the dance” does.
- Silero VAD voice-activity detection.
- WebRTC AEC3 echo cancellation.
- Welcome messages, silence continuation, proactive conversation, and goodbyes.
- Automatic goodbye when the configured session length is reached.
- Configurable waiting times.

## 6. Long-Term Memory

- Long-term fact extraction with mem0.
- Original text in local SQLite and vector indexes in Qdrant.
- Preferences, relationships, promises, emotional events, and session summaries.
- Pin important source lines and inject them separately.
- Inspect and delete memories.
- Role-play content is excluded from long-term memory by default.
- **6 embedding choices:** automatic, local MiniLM, Doubao, Qwen, OpenAI, or Gemini.
- Background index rebuilding after changing embedding providers.
- Automatic memory shutdown on low-spec devices to avoid excessive resource use.

## 7. 3D Stage and Performance

- **PMX (MMD), VRM, and GLB** support.
- Hot-swappable models.
- MMD cloth and rigid-body physics.
- Coordinated expressions, lip-sync, actions, dance, stance, and camera work.
- `[emo:]`, `[act:]`, `[intent:]`, `[dance:]`, `[cam:]`, and `[stand:]` performance tags.
- Automatic blinking, breathing, idle, listening, thinking, and speaking states.
- VMD dance and background music.
- Reviewed camera combinations to reduce clipping and mismatched movement.
- Six shot sizes.
- Physics, rendering resolution, lighting, and volume controls.
- 20 image backgrounds, six solid-color backgrounds, and custom images.
- Configurable stage-base texture, color, glow, and opacity.

## 8. Motion Capture and Interaction

- Real-time webcam motion capture.
- Local MP4/WebM motion-capture sources for repeatable tests.
- Body, hand, and face tracking with MediaPipe Holistic.
- Full PMX bone control and humanoid mapping for VRM/GLB.
- Body-area touch reactions.
- Shared touch behavior on the stage and desktop pet.
- Dragging the pet is not misinterpreted as touching.

## 9. Transparent Desktop Pet

- Always-on-top transparent window.
- Click-through empty space.
- Drag the character to move and drag a corner to resize.
- Remember position, size, display, and current character.
- Multiple displays and fallback to a visible workspace after disconnection.
- Walk while idle; stand still during conversation and dragging.
- Chat bubble and microphone beside the character.
- Minimize, reload, close, and return to the full stage.

## 10. Watch Together and Screen Understanding

- Off by default.
- Separate one-time screen looks and continuous watching.
- Local **MiniCPM-V 4.7 1B** vision process.
- Optional OpenAI-compatible vision providers.
- Continuous sliding video windows with real timestamps.
- Watch movies and short videos or listen to music together.
- Game understanding with League client state and local OCR.
- Subtitle timelines, scene policies, and language awareness.
- Video and sound stay on the computer; chat receives only short text summaries.
- No clicking or computer operation.
- Vision process exits when watching stops or the app closes.
- Local watch logs and recent-screenshot management.
- **MiniCPM-o 4.5 Omni test interface:** text, speech, and image input through ModelBest cloud or a self-hosted gateway.

## 11. Companionship Activities

- **9 tarot spreads**.
- 80 original Chinese-style card faces.
- Code-controlled deals and orientations.
- Spoken card drawing, clarification cards, redraws, and new readings.
- **22 scene cards**, plus scenes generated from memory.
- Keepsake album with screenshots, approximately eight-second clips, and per-character organization.
- Temporarily use a keepsake as the stage background.
- Rewrite, rewind, and perform the same reply again with a different emotion.
- Conversation history and backend talk logs.

## 12. Phantom Tavern

- Four-seat bluffing card game.
- Three model-driven AI opponents.
- Follow-or-challenge turns, a three-chamber revolver, and scoring.
- Four card-art styles.
- Cinematic judgments.
- Character voice performances.
- Speech does not freeze the table.
- Different voices can be assigned to table characters.

## 13. Games, Coding, and Livestreams

- Launch installed WeGame, Steam, and Epic games using natural language.
- Inspect the local game library and verify the process after launch.
- Open only the platform when a game is unavailable; never install it automatically.
- Code companion support for:
  - Cursor
  - Codex
  - Claude Code
  - Tongyi Lingma
  - Trae
  - Baidu Comate
- Recognize started, active, completed, and idle states.
- Douyin and Bilibili chat, follows, and gifts.
- Message aggregation, reconnect deduplication, and queue age/capacity controls.
- Actual playback receipts and recovery of unfinished gift responses.
- Local livestream rehearsal lab with scripted viewers, substitute models, fault injection, and persistent receipts.

## 14. Drawing, Web Lookup, and Coins

- Volcengine Seedream drawing.
- Image display, enlargement, and automatic keepsake archiving.
- Weather, stock prices, gold prices, exchange rates, news, and sports-score lookup.
- Local coin ledger without login or upload.
- Coins earned through online time and chat tokens.
- Wishing pool with 50 wishes per day.
- Three random props, coin rain, and spoken narration.
- Address-signed transfers, transfer-string imports, and burning.

## 15. Assets, Languages, and System Settings

- ZIP, RAR, and individual-file import.
- Automatic extraction, mojibake filename repair, and asset classification.
- VPD pose-to-VMD conversion.
- aplaybox search and download.
- A/B content-pack detection.
- Simplified Chinese, English, Japanese, and Korean.
- Independent interface and conversation languages.
- Fixed conversation language or automatic switching based on the user's current sentence.
- Independent toggles for memory, scenes, rewriting, keepsakes, tarot, Phantom Tavern, Code companion, touch, Harness, livestreams, and other modules.
- Configurable app logo and color theme.
- Windows A/B experience packs with bundled Chromium and Python runtime.
- Source development, Windows packaging, and local deployment.

## Companion Projects

- `companion-3d/`: early standalone 3D rendering and motion prototype.
- `music-api/`: independent music-search research API.

These companion projects are not core features of the main `companion/` product.
