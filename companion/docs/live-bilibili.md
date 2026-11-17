# B 站直播弹幕接入

直播控制台现在有两种 B 站接入方式。两种方式都只负责接收互动，不会替代直播姬或 OBS 推流。

## 直播姬 / OBS（房间号）

适合已经使用哔哩哔哩直播姬或 OBS 开播的场景：

1. 在“直播控制台 → 平台”选择“直播姬 / OBS（房间号）”。
2. 点击“扫码登录并自动连接”，用哔哩哔哩手机客户端扫码并确认。
3. 应用自动保存登录态、识别本人房间号并连接弹幕；也可以跳过扫码，手动填写房间号或 `https://live.bilibili.com/房间号`。
4. 直播姬继续负责画面和推流，不需要把账号密码交给本应用。

应用会先把短房间号转换为真实房间号，再获取 WBI 密钥、buvid3 和弹幕服务器 token，通过 `/sub` WebSocket 接收信息流。弹幕、礼物、醒目留言、上舰和点赞会统一转换为现有 `LiveEvent`，随后经过原来的去重、队列和主持流程。

Cookie 可以不填，但 B 站可能对游客连接隐藏昵称和 UID。扫码登录由用户主动触发，不读取浏览器或直播姬的本地凭据；成功后只保存 `SESSDATA`、`DedeUserID`、`DedeUserID__ckMd5` 和 `bili_jct`，用于识别观众和本人房间。不要把 Cookie 发给他人或提交到 Git。

## 开放平台（身份码）

原有方式保持不变，需要 Access Key ID、Access Key Secret、应用 ID 和主播身份码。它使用 `/v2/app/start` 创建官方互动会话，与网页房间信息流不是同一套鉴权。

## 协议依据与限制

- 官方开放平台文档：<https://open-live.bilibili.com/document/849b924b-b421-8586-3e5e-765a72ec3840>
- 直播间信息流社区协议整理：<https://janson20.github.io/bilibili-api-collect-mirror/docs/live/message_stream.html>
- `getDanmuInfo` 目前要求 WBI 签名和非空 `buvid3`；认证包使用真实房间 ID，压缩包可能使用 Brotli（proto=3）。
- 网页信息流属于非开放平台的兼容路径，B 站后续可能调整接口。真实房间联调仍需要主播本人的房间和网络环境。

## 用公开弹幕做端到端验证

下面的命令使用匿名公开弹幕，依次经过真实 WebSocket、接收入口、去重排队、主持选题、当前配置的真实对话模型，以及舞台 claim/ack 协议。它不会向房间发送消息，也不会修改用户的直播设置。

```powershell
.\companion\backend\.venv\Scripts\python.exe companion/backend/tools/verify_bili_live_e2e.py --room 1603600 --seconds 60 --output companion/artifacts/bili-live-e2e-1603600.json
```

报告中的 `playback_receipt=simulated_display_ack` 表示只验证了舞台播放协议，不能当作真实音频已经发声的证据；`audio_verified` 因而不是 `true`。

## 多人直播体验约束

- 私聊角色卡可能包含情侣关系、唯一用户或“宝”等固定称呼。直播提示词在角色卡之后显式切换为公开多人语境，保留性格但不沿用私密关系。
- 纯表情、孤立标点、`0` 等低信息弹幕不消耗模型调用；数字仍可由猜数字节目处理。
- 弹幕区同时显示最近一条“AI 回应”和它回复的观众，便于主播核对上下文。
- 真实页面验证覆盖 B 站匿名弹幕、连续模型回应、TTS 请求以及舞台 `completed` 回执；AI 说话期间新弹幕仍继续接收和排队。
