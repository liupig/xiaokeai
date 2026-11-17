# Live Show Engine V1 交付说明

## 交付边界

本模块包含 B 站双模式接入、匿名与扫码登录、观众身份归属、直播专用上下文、多人回复选题、确定性成语接龙、舞蹈指令、TTS/舞台回执、会话审计和交付验收。

个人聊天、陪玩、陪看不共享直播会话。只有真正开播才暂停个人输入与个人主动话术；仅连接弹幕不会改变个人逻辑。酒馆仍允许由用户主动使用。

## 直播会话审计

正式开播会在 `backend/data/live-journal.sqlite3` 创建独立会话，写入：

- `session_start` / `session_end`
- 平台连接状态
- 每条被接收入口的弹幕及平台消息 ID
- 每次生成的 turn、来源观众、文本、动作和时间
- 每次舞台 claim 对应的 completed / displayed / interrupted / failed ACK
- 模型失败

不会写入 Cookie、Access Secret、模型 Key 或个人聊天记录。

接口：

```text
GET /api/modules/live/sessions
GET /api/modules/live/sessions/{session_id}/trace?after=0&limit=500
GET /api/modules/live/sessions/{session_id}/metrics
```

指标包括评论数、turn 数、播放结果分布、模型失败数，以及来源弹幕到生成 turn 的平均/最大延迟。

## 一键验收

在仓库根目录执行：

```powershell
.\companion\backend\.venv\Scripts\python.exe companion/backend/tools/verify_live_delivery.py
```

报告写入 `companion/artifacts/live-delivery-acceptance.json`。它覆盖直播和个人/陪玩/陪看隔离回归，不冒充真实房间长时间稳定性证明。正式交付前仍需由运营完成真实房间试播和 OBS 画面/声音检查。

## 内容运行规则

- 正式直播普通弹幕通过原 `/api/chat` 入口，携带 `channel=live`、`viewer_name` 和 `live_session_id`；塔罗等原插件钩子与 TTS 继续复用，不另写直播版塔罗。
- `channel` 默认是 `personal`，个人请求保持不变。直播消息使用 `kind=live`，个人历史与直播历史分别读取。
- 普通回复按昵称区分观众和 AI 角色，不交换观众经历。
- 人少时最多等待约 0.5 秒聚合，后台选题 0.25 秒、页面状态 0.5 秒。
- 连续冷场采用 45、90、180、360 秒等递增间隔，新互动会重置。
- 成语接龙由状态机记录玩家、双方成语、重复、错误开头和下一回合。
- 舞蹈把原始弹幕传给选舞器，支持点名“极乐净土”等已有资产。
- 模型只负责口语表达，游戏规则和播放事实不交给模型猜测。

## 运营检查单

1. 选择“直播姬 / OBS（房间号）”，匿名连接或扫码登录。
2. 确认音色、模型、音乐与动作资产授权。
3. 用两名测试观众验证姓名、观点和连续话题不串线。
4. 完成一局成语接龙和一次点名舞蹈。
5. 检查 TTS、字幕、动作、BGM 和 OBS 采集是否同步。
6. 在会话指标中确认 ACK、模型失败和弹幕延迟。
7. 停播后确认个人聊天、陪玩、陪看恢复原有行为。
