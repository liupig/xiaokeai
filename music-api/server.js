/**
 * 音乐 API 服务 —— 数据源: 爱听音乐网 (2t58.com)
 *
 * GET /api/search?kw=关键词&page=1     搜索歌曲
 * GET /api/song/:id                    获取播放信息(音频直链/封面/歌词id)
 * GET /api/song/:id?title=1            同上,并附带歌曲标题(多一次页面请求,稍慢)
 * GET /api/lyric/:id                   获取 LRC 歌词(可带 ?lkid= 省一次请求)
 * GET /api/url/:id                     302 跳转到真实音频地址
 * GET /api/stream/:id                  代理播放音频流(规避跨域/防盗链)
 * GET /api/download/:id                下载音频(带正确文件名,浏览器直接另存为)
 */
'use strict';

const http = require('http');
const { TwoT58Client, sanitizeFilename } = require('./lib/twot58');

const PORT = Number(process.env.PORT || 3789);
const client = new TwoT58Client();

function json(res, code, data) {
  const body = JSON.stringify(data);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(body);
}

const routes = [
  {
    pattern: /^\/api\/search$/,
    async handle(req, res, url) {
      const kw = url.searchParams.get('kw') || url.searchParams.get('keyword');
      if (!kw) return json(res, 400, { code: 400, msg: '缺少参数 kw' });
      const page = Math.max(1, Number(url.searchParams.get('page')) || 1);
      json(res, 200, { code: 200, data: await client.search(kw, page) });
    },
  },
  {
    pattern: /^\/api\/song\/([^/]+)$/,
    async handle(req, res, url, m) {
      const song = await client.getSong(m[1]);
      if (url.searchParams.get('title')) song.title = await client.getSongTitle(m[1]);
      json(res, 200, { code: 200, data: song });
    },
  },
  {
    pattern: /^\/api\/lyric\/([^/]+)$/,
    async handle(req, res, url, m) {
      const lkid = url.searchParams.get('lkid');
      json(res, 200, { code: 200, data: await client.getLyric(m[1], lkid ? Number(lkid) : undefined) });
    },
  },
  {
    pattern: /^\/api\/url\/([^/]+)$/,
    async handle(req, res, url, m) {
      const song = await client.getSong(m[1]);
      res.writeHead(302, { Location: song.url, 'Access-Control-Allow-Origin': '*' });
      res.end();
    },
  },
  {
    pattern: /^\/api\/download\/([^/]+)$/,
    async handle(req, res, url, m) {
      const song = await client.getSong(m[1]);
      const title = (await client.getSongTitle(m[1])) || m[1];
      const ext = (song.url.split('?')[0].match(/\.(\w{2,4})$/)?.[1] || 'mp3').toLowerCase();
      const filename = `${sanitizeFilename(title)}.${ext}`;
      const upstream = await fetch(song.url, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
      });
      if (!upstream.ok || !upstream.body) return json(res, 502, { code: 502, msg: `下载失败 HTTP ${upstream.status}` });
      const headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': upstream.headers.get('content-type') || 'application/octet-stream',
        'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
      };
      const len = upstream.headers.get('content-length');
      if (len) headers['Content-Length'] = len;
      res.writeHead(200, headers);
      const reader = upstream.body.getReader();
      const pump = async () => {
        const { done, value } = await reader.read();
        if (done) return res.end();
        res.write(Buffer.from(value));
        return pump();
      };
      pump().catch(() => res.destroy());
    },
  },
  {
    pattern: /^\/api\/stream\/([^/]+)$/,
    async handle(req, res, url, m) {
      const song = await client.getSong(m[1]);
      const headers = { 'User-Agent': 'Mozilla/5.0' };
      if (req.headers.range) headers.Range = req.headers.range;
      const upstream = await fetch(song.url, { headers });
      const passHeaders = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': upstream.headers.get('content-type') || 'audio/mpeg',
      };
      for (const h of ['content-length', 'content-range', 'accept-ranges']) {
        const v = upstream.headers.get(h);
        if (v) passHeaders[h] = v;
      }
      res.writeHead(upstream.status, passHeaders);
      if (!upstream.body) return res.end();
      const reader = upstream.body.getReader();
      const pump = async () => {
        const { done, value } = await reader.read();
        if (done) return res.end();
        res.write(Buffer.from(value));
        return pump();
      };
      pump().catch(() => res.destroy());
    },
  },
];

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': '*',
    });
    return res.end();
  }
  if (url.pathname === '/' || url.pathname === '/api') {
    return json(res, 200, {
      code: 200,
      msg: '2t58 音乐 API',
      endpoints: [
        'GET /api/search?kw=关键词&page=1',
        'GET /api/song/:id (?title=1 附带标题)',
        'GET /api/lyric/:id (?lkid= 可选)',
        'GET /api/url/:id (302 跳转音频)',
        'GET /api/stream/:id (代理音频流)',
        'GET /api/download/:id (带文件名下载)',
      ],
    });
  }
  for (const route of routes) {
    const m = url.pathname.match(route.pattern);
    if (m) {
      try {
        return await route.handle(req, res, url, m);
      } catch (err) {
        return json(res, 502, { code: 502, msg: err.message });
      }
    }
  }
  json(res, 404, { code: 404, msg: '接口不存在' });
});

server.listen(PORT, () => {
  console.log(`音乐 API 服务已启动: http://localhost:${PORT}`);
});
