"""本地 TTS 分句：先按标点切，只有中间还很长、没有符号时才用结巴。

例：「小哥哥怎么突然撒娇呀？（指尖轻点你的额头）小心我告诉阿姨你乱要辈分哦。」
→ 小哥哥怎么突然撒娇呀？
→ （指尖轻点你的额头）
→ 小心我告诉阿姨你乱要辈分哦。
"""
from __future__ import annotations

import logging
import re
from typing import List, Tuple

HARD_END = re.compile(r"[。！？!?；;\n]|…{1,3}|\.{3,}")
SOFT_END = re.compile(r"[，、：:～~）\)」』】]")
# 切开后符号留在前一段
PUNCT_KEEP = re.compile(r"(?<=[。！？!?；;，、：:～~…）\)」』】])")
PUNCT_ANY = re.compile(r"[。！？!?；;，、：:～~…）\)」』】\n]")
PUNCT_ONLY = re.compile(r"^[。！？!?；;，、：:～~…）\)」』】\s]+$")
STICKY = set("的了着过呢吗吧啊呀哦噢嘛啦喽呵哈")
CLOSE_END = re.compile(r"[）\)」』】]")

TARGET_MAX = 20
HARD_MAX = 22
MIN_SOFT = 8
# 未完成的逗号从句不要单独送 TTS：Qwen 会把半句话接着含糊往下编。
SENTENCE_MAX = 36
# 两句加起来不超过这么长就并成一段。
MERGE_MAX = 15

_jieba_ok: bool | None = None


def _ensure_jieba() -> bool:
    global _jieba_ok
    if _jieba_ok is not None:
        return _jieba_ok
    try:
        import jieba
        jieba.setLogLevel(logging.WARNING)
        jieba.initialize()
        _jieba_ok = True
    except Exception as e:
        print(f"[speech_split] jieba 不可用，退回标点分句：{e}")
        _jieba_ok = False
    return _jieba_ok


def _words(text: str) -> List[str]:
    if _ensure_jieba():
        import jieba
        raw = [w for w in jieba.lcut(text, cut_all=False, HMM=True) if w]
    else:
        raw = re.findall(r"[A-Za-z0-9]+|[。！？!?；;，、：:～~…）\)」』】]+|[^\s]", text or "")
    out: List[str] = []
    for w in raw:
        if not w:
            continue
        if out and (PUNCT_ONLY.match(w) or w in STICKY):
            out[-1] += w
        else:
            out.append(w)
    return out


def pack_words(words: List[str], max_len: int = TARGET_MAX) -> List[str]:
    chunks: List[str] = []
    cur = ""
    for w in words:
        if not cur:
            if len(w) <= max_len:
                cur = w
                continue
            for i in range(0, len(w), max_len):
                piece = w[i:i + max_len]
                if i + max_len < len(w):
                    chunks.append(piece)
                else:
                    cur = piece
            continue
        if len(cur) + len(w) <= max_len:
            cur += w
        else:
            chunks.append(cur)
            if len(w) <= max_len:
                cur = w
            else:
                for i in range(0, len(w), max_len):
                    piece = w[i:i + max_len]
                    if i + max_len < len(w):
                        chunks.append(piece)
                    else:
                        cur = piece
    if cur:
        chunks.append(cur)
    return chunks


def split_punct(text: str) -> List[str]:
    """按符号切开，符号跟前一段。没有符号就整段返回。"""
    s = (text or "").strip()
    if not s:
        return []
    parts = [p.strip() for p in PUNCT_KEEP.split(s) if p.strip()]
    return parts or [s]


def glue_parts(parts: List[str]) -> List[str]:
    """逗号切开的碎段并回去：能装进 TARGET_MAX 就并；更长的句子才切开。"""
    out: List[str] = []
    buf = ""
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if not buf:
            buf = p
            continue
        n = len(buf) + len(p)
        if n <= TARGET_MAX:
            buf += p
            continue
        out.append(buf)
        buf = p
    if buf:
        out.append(buf)
    return out


def pack_complete(text: str) -> List[str]:
    """完整短句整段送；超过 SENTENCE_MAX 才按逗号拆成约 20 字。"""
    s = (text or "").strip()
    if not s:
        return []
    complete = bool(HARD_END.search(s))
    if len(s) <= SENTENCE_MAX and (complete or len(s) <= TARGET_MAX):
        return [s]
    glued = glue_parts(split_punct(s))
    out: List[str] = []
    for part in glued:
        if len(part) <= TARGET_MAX:
            out.append(part)
        else:
            out.extend(c for c in pack_words(_words(part)) if c.strip())
    return [c for c in out if c.strip()]


def pack_stream(text: str) -> Tuple[List[str], str]:
    """无标点的长段才结巴；最后一个词先留着，避免截半截。"""
    s = text or ""
    if len(s) < TARGET_MAX or PUNCT_ANY.search(s):
        return [], s
    words = _words(s)
    if len(words) <= 1:
        if len(s) >= HARD_MAX:
            return pack_words(words) or [s[:TARGET_MAX]], s[TARGET_MAX:] if len(s) > TARGET_MAX else ""
        return [], s
    tail = words.pop()
    chunks = [c for c in pack_words(words) if c.strip()]
    return chunks, tail


class SentenceSplitter:
    def __init__(self) -> None:
        self.buf = ""

    def feed(self, delta: str) -> List[str]:
        if not delta:
            return []
        self.buf += delta
        out: List[str] = []
        out.extend(self._drain_hard())
        out.extend(self._drain_soft())
        out.extend(self._drain_jieba())
        return [s for s in out if s.strip()]

    def flush(self) -> List[str]:
        left = self.buf
        self.buf = ""
        return [s for s in pack_complete(left) if s.strip()]

    def _drain_hard(self) -> List[str]:
        out: List[str] = []
        while self.buf:
            m = HARD_END.search(self.buf)
            if not m:
                break
            piece = self.buf[: m.end()]
            self.buf = self.buf[m.end():]
            if piece.strip():
                out.extend(pack_complete(piece))
        return out

    def _drain_soft(self) -> List[str]:
        """括号可以切；逗号要等整句（。！？）或已经超过 SENTENCE_MAX。"""
        out: List[str] = []
        while self.buf:
            m = SOFT_END.search(self.buf)
            if not m:
                break
            end = m.end()
            piece = self.buf[:end]
            is_close = bool(CLOSE_END.match(m.group()))
            if not is_close and len(piece) < SENTENCE_MAX:
                break
            out.extend(pack_complete(piece))
            nxt = self.buf[end:]
            if nxt == self.buf:
                break
            self.buf = nxt
        return out

    def _drain_jieba(self) -> List[str]:
        """缓冲里已经没有任何可切符号，还是太长，才结巴。"""
        out: List[str] = []
        while len(self.buf) >= TARGET_MAX and not PUNCT_ANY.search(self.buf):
            if self.buf.count("（") + self.buf.count("(") > self.buf.count("）") + self.buf.count(")"):
                break
            before = self.buf
            chunks, rest = pack_stream(self.buf)
            if not chunks:
                if len(self.buf) >= HARD_MAX:
                    out.append(self.buf[:TARGET_MAX])
                    self.buf = self.buf[TARGET_MAX:]
                    continue
                break
            out.extend(chunks)
            self.buf = rest
            if self.buf == before:
                break
        return out
