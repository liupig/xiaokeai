# 音乐 API 服务(数据源:爱听音乐网 2t58.com)

零依赖的 Node.js 音乐接口服务,封装了 [爱听音乐网](https://www.2t58.com/) 的搜索、播放直链解密、歌词获取能力。

> 仅供学习研究,请勿用于商业用途。音源实际来自酷我 CDN,直链有时效性,播放前应实时获取。

## 运行

```bash
node server.js          # 默认端口 3789
PORT=8080 node server.js
```

要求 Node.js ≥ 18.14(使用内置 fetch),无需 npm install。

## 接口

### 1. 搜索歌曲

```
GET /api/search?kw=刘德华&page=1
```

```json
{
  "code": 200,
  "data": {
    "keyword": "刘德华", "page": 1, "pageSize": 60, "total": 3600,
    "songs": [
      { "id": "ZG12bm53", "title": "刘德华 - 忘情水", "artist": "刘德华", "name": "忘情水",
        "pageUrl": "https://www.2t58.com/song/ZG12bm53.html" }
    ]
  }
}
```

注意:部分版权敏感关键词(如"周杰伦")已被站方屏蔽,会返回空结果。

### 2. 获取播放信息(音频直链)

```
GET /api/song/:id            # id 为搜索结果中的歌曲 id
GET /api/song/:id?title=1    # 附带歌曲标题(多一次页面请求,稍慢)
```

```json
{
  "code": 200,
  "data": {
    "id": "ZG12bm53",
    "lkid": 325771,
    "pic": "http://img2.kuwo.cn/star/albumcover/500/s4s21/30/3195131112.jpg",
    "url": "https://car-lw.kuwo.cn/.../C200001lRTEO0PeZKl.m4a?from=vip",
    "title": "刘德华 - 忘情水"
  }
}
```

### 3. 获取 LRC 歌词

```
GET /api/lyric/:id                 # 自动请求一次 play.php 拿 lkid
GET /api/lyric/:id?lkid=325771     # 已有 lkid 时可省一次请求
```

### 4. 音频直链跳转 / 流代理

```
GET /api/url/:id       # 302 跳转到真实音频地址,可直接塞给 <audio src>
GET /api/stream/:id    # 服务端代理音频流,支持 Range 断点续传,规避跨域
GET /api/download/:id  # 下载音频,带正确文件名(浏览器直接另存为「歌手 - 歌名.m4a」)
```

## 下载歌曲

### 方式一:命令行工具(推荐,可批量)

```bash
node download.js <歌曲id> [歌曲id...]      # 按 id 下载
node download.js -s "刘德华"               # 搜索后下载第 1 首
node download.js -s "刘德华" -n 5          # 下载前 5 首
node download.js -s "刘德华" --all --lrc   # 下载整页结果并保存歌词
```

选项:`-o/--out 目录`(默认 `./downloads`)、`-n/--num N`、`--all`、`--lrc`(附带歌词)、`-h`。
文件自动命名为「歌手 - 歌名.扩展名」(音源多为 `.m4a`)。

### 方式二:浏览器 / 下载器

启动服务后直接访问 `http://localhost:3789/api/download/歌曲id`,浏览器会以正确文件名另存为。

### 方式三:代码调用

```js
const { TwoT58Client } = require('./lib/twot58');
const client = new TwoT58Client();
const { songs } = await client.search('刘德华');
await client.download(songs[0].id, './downloads', { withLyric: true });
```

## 实现原理

| 环节 | 说明 |
|---|---|
| 人机验证 | 站点 HTML 页面首访返回验证表单,自动提交 `csrf_token + human_check` 获取 session cookie(约 1 小时有效,失效后自动重新验证) |
| 搜索 | `GET /so/{UTF-8 关键词}/{页码}.html`,正则解析结果列表 |
| 播放直链 | `POST /js/play.php`(`id`,`type=music`),返回的 `url` 为 AES-256-ECB 加密的 hex,密钥 = `SHA256("SklaBTy1aTSEEtMjAyNg")`,PKCS7 填充 |
| 密钥兜底 | 若站方轮换密钥导致本地解密失败,自动拉取其前端混淆脚本 `playen.js` 在 Node vm 沙箱中调用原版 `decodeUrl` 解密 |
| 歌词 | `GET js.eev3.com/lrc.php?cid={lkid}`,`lkid` 来自 play.php 响应 |

## 文件结构

```
music-api/
├── server.js        # HTTP 服务与路由
├── download.js      # 命令行批量下载工具
├── lib/twot58.js    # 2t58 客户端(会话/验证/解密/解析/下载)
└── package.json
```
