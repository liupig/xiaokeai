/**
 * 与后端 speech_split.py 同一套：先标点，长段没符号才按词切。
 * 前端无 jieba；真正对话走后端。
 */

const HARD_END = /[。！？!?；;\n]|…{1,3}|\.{3,}/;
const SOFT_END = /[，、：:～~）)」』】]/;
const PUNCT_KEEP = /(?<=[。！？!?；;，、：:～~…）)」』】])/;
const PUNCT_ANY = /[。！？!?；;，、：:～~…）)」』】\n]/;
const CLOSE_END = /[）)」』】]/;
const STICKY = new Set('的了着过呢吗吧啊呀哦噢嘛啦喽呵哈'.split(''));
const TARGET_MAX = 20;
const HARD_MAX = 22;
const MIN_SOFT = 8;
const SENTENCE_MAX = 36;
const MERGE_MAX = 15;

function charLen(s: string) {
  return Array.from(s).length;
}

function tokens(text: string): string[] {
  const raw = text.match(/[A-Za-z0-9]+|[。！？!?；;，、：:～~…）)」』】]+|[^\s]/g) || [];
  const out: string[] = [];
  for (const w of raw) {
    if (!w) continue;
    const punct = /^[。！？!?；;，、：:～~…）)」』】\s]+$/.test(w);
    if (out.length && (punct || STICKY.has(w))) out[out.length - 1] += w;
    else out.push(w);
  }
  return out;
}

function packWords(words: string[], maxLen = TARGET_MAX): string[] {
  const chunks: string[] = [];
  let cur = '';
  const pushLong = (w: string) => {
    const chars = Array.from(w);
    for (let i = 0; i < chars.length; i += maxLen) {
      const piece = chars.slice(i, i + maxLen).join('');
      if (i + maxLen < chars.length) chunks.push(piece);
      else cur = piece;
    }
  };
  for (const w of words) {
    if (!cur) {
      if (charLen(w) <= maxLen) cur = w;
      else pushLong(w);
      continue;
    }
    if (charLen(cur + w) <= maxLen) cur += w;
    else {
      chunks.push(cur);
      if (charLen(w) <= maxLen) cur = w;
      else {
        cur = '';
        pushLong(w);
      }
    }
  }
  if (cur) chunks.push(cur);
  return chunks;
}

function splitPunct(text: string): string[] {
  const s = text.trim();
  if (!s) return [];
  const parts = s.split(PUNCT_KEEP).map((p) => p.trim()).filter(Boolean);
  return parts.length ? parts : [s];
}

function glueParts(parts: string[]): string[] {
  const out: string[] = [];
  let buf = '';
  for (const raw of parts) {
    const p = raw.trim();
    if (!p) continue;
    if (!buf) {
      buf = p;
      continue;
    }
    const n = charLen(buf) + charLen(p);
    if (n <= TARGET_MAX) {
      buf += p;
      continue;
    }
    out.push(buf);
    buf = p;
  }
  if (buf) out.push(buf);
  return out;
}

function packComplete(text: string): string[] {
  const s = text.trim();
  if (!s) return [];
  const complete = HARD_END.test(s);
  if (charLen(s) <= SENTENCE_MAX && (complete || charLen(s) <= TARGET_MAX)) return [s];
  const out: string[] = [];
  for (const part of glueParts(splitPunct(s))) {
    if (charLen(part) <= TARGET_MAX) out.push(part);
    else out.push(...packWords(tokens(part)).filter((c) => c.trim()));
  }
  return out.filter((c) => c.trim());
}

export class SpeechSplitter {
  private buf = '';

  reset() {
    this.buf = '';
  }

  feed(delta: string): string[] {
    if (!delta) return [];
    this.buf += delta;
    const out: string[] = [];
    out.push(...this.drainHard());
    out.push(...this.drainSoft());
    out.push(...this.drainJieba());
    return out.filter((s) => s.trim());
  }

  flush(): string[] {
    const left = this.buf;
    this.buf = '';
    return packComplete(left);
  }

  private drainHard(): string[] {
    const out: string[] = [];
    while (this.buf) {
      const m = this.buf.match(HARD_END);
      if (!m || m.index == null) break;
      const end = m.index + m[0].length;
      const piece = this.buf.slice(0, end);
      this.buf = this.buf.slice(end);
      if (piece.trim()) out.push(...packComplete(piece));
    }
    return out;
  }

  private drainSoft(): string[] {
    const out: string[] = [];
    while (this.buf) {
      const m = this.buf.match(SOFT_END);
      if (!m || m.index == null) break;
      const end = m.index + m[0].length;
      const piece = this.buf.slice(0, end);
      const isClose = CLOSE_END.test(m[0]);
      if (!isClose && charLen(piece) < SENTENCE_MAX) break;
      out.push(...packComplete(piece));
      this.buf = this.buf.slice(end);
    }
    return out;
  }

  private drainJieba(): string[] {
    const out: string[] = [];
    while (charLen(this.buf) >= TARGET_MAX && !PUNCT_ANY.test(this.buf)) {
      const open = (this.buf.split('（').length - 1) + (this.buf.split('(').length - 1);
      const close = (this.buf.split('）').length - 1) + (this.buf.split(')').length - 1);
      if (open > close) break;
      const words = tokens(this.buf);
      if (words.length <= 1) {
        if (charLen(this.buf) >= HARD_MAX) {
          const chars = Array.from(this.buf);
          out.push(chars.slice(0, TARGET_MAX).join(''));
          this.buf = chars.slice(TARGET_MAX).join('');
          continue;
        }
        break;
      }
      const tail = words.pop()!;
      const chunks = packWords(words).filter((c) => c.trim());
      if (!chunks.length) break;
      out.push(...chunks);
      this.buf = tail;
    }
    return out;
  }
}
