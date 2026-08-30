/**
 * 爱听音乐网 (2t58.com) 客户端
 *
 * 站点机制说明:
 * 1. HTML 页面(搜索页/歌曲页)受"人机验证"拦截: 首次访问返回验证表单,
 *    需 POST csrf_token + human_check 换取 session cookie(约 1 小时有效)。
 * 2. 播放接口 POST /js/play.php (id, type=music) 返回 JSON,其中 url 字段
 *    是 AES-256-ECB 加密后的 hex 字符串,密钥为 SHA256(口令) ,PKCS7 填充。
 * 3. 歌词接口 GET https://js.eev3.com/lrc.php?cid={lkid},lkid 来自 play.php 响应。
 */
'use strict';

const crypto = require('crypto');
const vm = require('vm');

const BASE = 'https://www.2t58.com';
const LRC_API = 'https://js.eev3.com/lrc.php';
const PLAYEN_JS = 'https://js.eev3.com/js/playen.js';
const CRYPTO_JS = 'https://js.eev3.com/js/crypto.js';

// decodeUrl 使用的口令(从 playen.js 逆向得到), AES 密钥 = SHA256(口令)
const AES_PASSPHRASE = 'SklaBTy1aTSEEtMjAyNg';

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';

/** 去除文件名中的非法字符(Windows/*nix 通用) */
function sanitizeFilename(name) {
  return name
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120);
}

class TwoT58Client {
  constructor() {
    this.cookies = new Map();
    this.vmDecoder = null; // 密钥失效时的兜底解码器
  }

  // ---------- 基础 HTTP(带 cookie 会话) ----------

  cookieHeader() {
    return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join('; ');
  }

  storeCookies(res) {
    for (const line of res.headers.getSetCookie?.() ?? []) {
      const [pair] = line.split(';');
      const eq = pair.indexOf('=');
      if (eq > 0) this.cookies.set(pair.slice(0, eq).trim(), pair.slice(eq + 1).trim());
    }
  }

  async request(url, { method = 'GET', body = null, headers = {} } = {}) {
    // 手动处理重定向,否则中间响应的 set-cookie 会丢失
    for (let hop = 0; hop < 5; hop++) {
      const res = await fetch(url, {
        method,
        body,
        redirect: 'manual',
        headers: {
          'User-Agent': UA,
          Referer: BASE + '/',
          ...(this.cookies.size ? { Cookie: this.cookieHeader() } : {}),
          ...headers,
        },
      });
      this.storeCookies(res);
      if (res.status >= 300 && res.status < 400 && res.headers.get('location')) {
        url = new URL(res.headers.get('location'), url).href;
        method = 'GET';
        body = null;
        continue;
      }
      return res;
    }
    throw new Error('重定向次数过多: ' + url);
  }

  /** 获取 HTML 页面,自动通过人机验证 */
  async fetchPage(url) {
    let html = await (await this.request(url)).text();
    if (html.includes('verifyForm') || html.includes('安全人机验证')) {
      const token = html.match(/name="csrf_token"\s+value="([0-9a-f]+)"/)?.[1];
      if (!token) throw new Error('无法解析人机验证 csrf_token');
      await (
        await this.request(url, {
          method: 'POST',
          body: new URLSearchParams({ csrf_token: token, human_check: 'on' }).toString(),
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
      ).text();
      // 验证 POST 的响应可能是 JS 跳转中间页,拿到 session cookie 后重新 GET 一次
      html = await (await this.request(url)).text();
      if (html.includes('verifyForm')) throw new Error('人机验证未通过');
    }
    return html;
  }

  // ---------- URL 解密 ----------

  decryptUrl(hexCipher) {
    const key = crypto.createHash('sha256').update(AES_PASSPHRASE).digest();
    const decipher = crypto.createDecipheriv('aes-256-ecb', key, null);
    const out = Buffer.concat([decipher.update(Buffer.from(hexCipher, 'hex')), decipher.final()]);
    return out.toString('utf8');
  }

  /** 兜底: 站方轮换密钥时,拉取其混淆 JS 在沙箱中调用 decodeUrl */
  async vmDecodeUrl(hexCipher) {
    if (!this.vmDecoder) {
      const [cryptoSrc, playenSrc] = await Promise.all(
        [CRYPTO_JS, PLAYEN_JS].map((u) => fetch(u, { headers: { 'User-Agent': UA } }).then((r) => r.text()))
      );
      const stub = new Proxy(function () {}, {
        get: (t, p) => (p === Symbol.toPrimitive ? () => '' : stub),
        apply: () => stub,
      });
      const noop = () => stub;
      const sandbox = {
        navigator: { userAgent: UA },
        location: { href: BASE + '/', hostname: 'www.2t58.com', protocol: 'https:' },
        document: {
          createElement: () => ({ style: {}, setAttribute: noop, appendChild: noop }),
          getElementById: () => null,
          addEventListener: noop,
          referrer: '',
          cookie: '',
        },
        setInterval: () => 0,
        setTimeout: () => 0,
        clearInterval: noop,
        alert: noop,
        jQuery: stub,
        $: stub,
        console: { log: noop, warn: noop, error: noop, info: noop, debug: noop, table: noop, trace: noop },
      };
      sandbox.window = sandbox;
      sandbox.self = sandbox;
      sandbox.top = sandbox;
      vm.createContext(sandbox);
      vm.runInContext(cryptoSrc, sandbox, { timeout: 5000 });
      vm.runInContext(playenSrc, sandbox, { timeout: 5000 });
      this.vmDecoder = (cipher) =>
        vm.runInContext(`decodeUrl(${JSON.stringify(cipher)})`, sandbox, { timeout: 5000 });
    }
    return this.vmDecoder(hexCipher);
  }

  async decodeUrl(hexCipher) {
    try {
      const url = this.decryptUrl(hexCipher);
      if (/^https?:\/\//.test(url)) return url;
    } catch {
      /* 密钥可能已轮换,走沙箱兜底 */
    }
    const url = await this.vmDecodeUrl(hexCipher);
    if (!/^https?:\/\//.test(String(url))) throw new Error('音频链接解密失败');
    return url;
  }

  // ---------- 业务接口 ----------

  /**
   * 搜索歌曲
   * @param {string} keyword 关键词(注: 部分版权敏感词如"周杰伦"被站方屏蔽,会返回空结果)
   * @param {number} page 页码,从 1 开始
   */
  async search(keyword, page = 1) {
    const url = `${BASE}/so/${encodeURIComponent(keyword)}/${page}.html`;
    const html = await this.fetchPage(url);
    if (html.includes('没有找到该关键词')) return { keyword, page, total: 0, songs: [] };

    const total = Number(html.match(/共有<span>(\d+)<\/span>首/)?.[1] ?? 0);
    const listHtml = html.slice(html.indexOf('play_list'));
    const songs = [];
    const re = /<div class="name"><a href="\/song\/([^."]+)\.html"[^>]*>([^<]+)<\/a>/g;
    let m;
    while ((m = re.exec(listHtml))) {
      const [artist, ...rest] = m[2].split(' - ');
      songs.push({
        id: m[1],
        title: m[2].trim(),
        artist: rest.length ? artist.trim() : null,
        name: rest.length ? rest.join(' - ').trim() : m[2].trim(),
        pageUrl: `${BASE}/song/${m[1]}.html`,
      });
    }
    return { keyword, page, pageSize: songs.length, total, songs };
  }

  /**
   * 获取歌曲播放信息(真实音频直链、封面、歌词 id)
   * @param {string} id 歌曲 id,即 /song/{id}.html 中的 id
   */
  async getSong(id) {
    const res = await this.request(`${BASE}/js/play.php`, {
      method: 'POST',
      body: new URLSearchParams({ id, type: 'music' }).toString(),
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        Referer: `${BASE}/song/${id}.html`,
      },
    });
    const data = await res.json();
    if (data.msg !== 1) throw new Error(data.error || '歌曲不存在或接口失败');
    return {
      id,
      lkid: data.lkid,
      pic: data.pic || null,
      url: await this.decodeUrl(data.url),
      pageUrl: `${BASE}/song/${id}.html`,
    };
  }

  /** 获取歌曲标题(需请求歌曲详情页,略慢) */
  async getSongTitle(id) {
    try {
      const html = await this.fetchPage(`${BASE}/song/${id}.html`);
      const t = html.match(/<title>([^<]+?)MP3免费下载/)?.[1];
      return t ? t.trim() : null;
    } catch {
      return null;
    }
  }

  /**
   * 下载歌曲到本地文件
   * @param {string} id 歌曲 id
   * @param {string} dir 保存目录
   * @param {object} [opts]
   * @param {boolean} [opts.withLyric] 是否同时保存 .lrc 歌词
   * @param {(p:{received:number,total:number})=>void} [opts.onProgress] 进度回调
   * @returns {Promise<{file:string, title:string, bytes:number, lyricFile:string|null}>}
   */
  async download(id, dir, opts = {}) {
    const fs = require('fs');
    const fsp = fs.promises;
    const path = require('path');

    const song = await this.getSong(id);
    const title = (await this.getSongTitle(id)) || id;
    const ext = (song.url.split('?')[0].match(/\.(\w{2,4})$/)?.[1] || 'mp3').toLowerCase();
    const safeName = sanitizeFilename(title);
    await fsp.mkdir(dir, { recursive: true });
    const file = path.join(dir, `${safeName}.${ext}`);

    // 酷我 CDN 对 2t58 Referer 会返回 403，只带 UA 即可
    const res = await fetch(song.url, { headers: { 'User-Agent': UA } });
    if (!res.ok || !res.body) throw new Error(`下载失败 HTTP ${res.status}`);
    const total = Number(res.headers.get('content-length')) || 0;

    const out = fs.createWriteStream(file);
    const reader = res.body.getReader();
    let received = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.length;
      out.write(Buffer.from(value));
      opts.onProgress?.({ received, total });
    }
    await new Promise((resolve, reject) => out.end((err) => (err ? reject(err) : resolve())));

    let lyricFile = null;
    if (opts.withLyric) {
      try {
        const { lrc } = await this.getLyric(id, song.lkid);
        if (lrc && !lrc.includes('暂无歌词')) {
          lyricFile = path.join(dir, `${safeName}.lrc`);
          await fsp.writeFile(lyricFile, lrc, 'utf8');
        }
      } catch {
        /* 歌词可选,失败忽略 */
      }
    }
    return { file, title, bytes: received, lyricFile };
  }

  /**
   * 获取 LRC 歌词
   * @param {string} id 歌曲 id
   * @param {number} [lkid] play.php 返回的歌词 id,不传则自动请求一次 play.php
   */
  async getLyric(id, lkid) {
    if (!lkid) {
      const song = await this.getSong(id);
      lkid = song.lkid;
    }
    const res = await fetch(`${LRC_API}?cid=${lkid}`, {
      headers: { 'User-Agent': UA, Referer: BASE + '/' },
    });
    const data = await res.json();
    return { id, lkid, lrc: data.lrc || '' };
  }
}

module.exports = { TwoT58Client, BASE, sanitizeFilename };
