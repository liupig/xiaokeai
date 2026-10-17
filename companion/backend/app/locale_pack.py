"""语言包。companion/locales/{lang}/ 下的 JSON，前后端读同一份。

对话语言用 contextvar 传给这一轮的 prompt、口令和分句。
老用户没存 locale 时按 zh-CN。
"""
from __future__ import annotations

import json
import os
import re
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Optional

_reply: ContextVar[str] = ContextVar("companion_reply", default="zh-CN")
_cache: Dict[str, Dict[str, Any]] = {}
_re_cache: Dict[tuple, re.Pattern] = {}
_lock = threading.Lock()

SUPPORTED = ("zh-CN", "en", "ja", "ko")

_ZH_IGNORECASE = {"roleplay.enter", "roleplay.inject", "classify.dance"}

BCP = {"zh-CN": "zh-CN", "en": "en-US", "ja": "ja-JP", "ko": "ko-KR"}

EDGE_DEFAULT = {
    "zh-CN": "zh-CN-XiaoyiNeural",
    "en": "en-US-AriaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
}
QWEN_DEFAULT = {
    "zh-CN": "Serena",
    "en": "Serena",
    "ja": "Ono_Anna",
    "ko": "Sohee",
}
VOLC_DEFAULT = {
    "zh-CN": "zh_female_vv_uranus_bigtts",
    "en": "en_female_dacey_uranus_bigtts",
    "ja": "ja_female_bv522_uranus_bigtts",
    "ko": "ko_female_bv546_uranus_bigtts",
}
# 本地英语只有男声。英语默认用中文女声的音色，合成时把语言标成 English。
_QWEN_EN_FEMALE = {"Serena", "Vivian"}
_QWEN_LANG = {
    "Vivian": "zh-CN", "Serena": "zh-CN", "Uncle_Fu": "zh-CN",
    "Dylan": "zh-CN", "Eric": "zh-CN",
    "Ryan": "en", "Aiden": "en",
    "Ono_Anna": "ja", "Sohee": "ko",
}

_LATIN_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_LATIN_KEEP = {
    "ok", "hi", "hey", "yeah", "yes", "no", "hmm", "oh", "lol",
    "api", "vrm", "mmd", "pmx", "glb", "tts", "asr",
}


def locales_dir() -> Path:
    env = (os.environ.get("COMPANION_ROOT") or "").strip()
    if env:
        packed = Path(env) / "locales"
        if packed.is_dir():
            return packed
    return Path(__file__).resolve().parents[2] / "locales"


def normalize(code: str | None) -> str:
    c = (code or "").strip().replace("_", "-")
    low = c.lower()
    if low in ("en", "en-us", "en-gb"):
        return "en"
    if low in ("zh", "zh-cn", "zh-hans", "zh-sg"):
        return "zh-CN"
    if low.startswith("ja"):
        return "ja"
    if low.startswith("ko"):
        return "ko"
    if c in SUPPORTED:
        return c
    return "zh-CN"


def bcp(lang: str | None) -> str:
    return BCP.get(normalize(lang), "zh-CN")


def set_reply(lang: str | None) -> None:
    _reply.set(normalize(lang))


def current_reply() -> str:
    return normalize(_reply.get())


def reply_of(conf: Dict[str, Any] | None) -> str:
    loc = (conf or {}).get("locale") or {}
    return normalize(loc.get("reply") or "zh-CN")


def ui_of(conf: Dict[str, Any] | None) -> str:
    loc = (conf or {}).get("locale") or {}
    return normalize(loc.get("ui") or "zh-CN")


def detect_script(text: str) -> Optional[str]:
    """整句明显是另一种文字才返回语言。夹一两个英文词返回 None。"""
    s = re.sub(r"\[[a-z]+:[^\]]+\]", " ", text or "")
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    kana = len(re.findall(r"[\u3040-\u30ff]", s))
    hang = len(re.findall(r"[\uac00-\ud7af]", s))
    words = _LATIN_WORD.findall(s)
    if kana >= 2 and kana >= hang and kana + cjk >= 2 and (kana >= 2 or cjk < kana * 4):
        return "ja"
    if hang >= 2 and hang >= cjk and hang >= len("".join(words)):
        return "ko"
    if cjk == 0 and kana == 0 and hang == 0 and words:
        content = [w for w in words if w.lower() not in _LATIN_KEEP]
        if len(words) >= 3 or len(content) >= 2:
            return "en"
        return None
    if cjk >= 2 and kana == 0 and hang == 0:
        latin = sum(len(w) for w in words)
        if latin > cjk:
            return None
        return "zh-CN"
    return None


def resolve_turn(conf: Dict[str, Any] | None, text: str, mode: str) -> str:
    loc = (conf or {}).get("locale") or {}
    reply = normalize(loc.get("reply") or "zh-CN")
    if (loc.get("reply_mode") or "fixed") != "follow":
        return reply
    if (mode or "user").lower() != "user":
        return reply
    found = detect_script(text or "")
    if found and found != reply:
        return found
    return reply


def load(lang: str, name: str) -> Dict[str, Any]:
    lang = normalize(lang)
    key = f"{lang}/{name}"
    with _lock:
        if key in _cache:
            return _cache[key]
    path = locales_dir() / lang / name
    data: Dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    if not data and lang != "en":
        data = load("en", name) if lang != "zh-CN" else {}
    with _lock:
        _cache[key] = data
    return data


def prompts(lang: str | None = None) -> Dict[str, Any]:
    return load(lang or current_reply(), "prompts.json")


def intents(lang: str | None = None) -> Dict[str, Any]:
    return load(lang or current_reply(), "intents.json")


def content(lang: str | None = None) -> Dict[str, Any]:
    return load(lang or current_reply(), "content.json")


def has_feature(lang: str | None, feature: str) -> bool:
    pack = content(lang)
    if pack.get("builtin"):
        return True
    return bool(pack.get(feature))


def _dig(node: Any, dotted: str) -> Any:
    cur = node
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def intent_pattern(lang: str | None, dotted: str) -> str:
    lang = normalize(lang or current_reply())
    raw = _dig(intents(lang), dotted)
    if isinstance(raw, str) and raw:
        return raw
    if lang != "zh-CN":
        raw = _dig(intents("en"), dotted)
        if isinstance(raw, str):
            return raw
    raw = _dig(intents("zh-CN"), dotted)
    return raw if isinstance(raw, str) else "$^"


def compile_intent(lang: str | None, dotted: str) -> re.Pattern:
    lang = normalize(lang or current_reply())
    key = (lang, dotted)
    hit = _re_cache.get(key)
    if hit is not None:
        return hit
    flags = 0
    if lang != "zh-CN" or dotted in _ZH_IGNORECASE:
        flags = re.IGNORECASE
    pat = re.compile(intent_pattern(lang, dotted), flags)
    _re_cache[key] = pat
    return pat


class LangRe:
    """按当前对话语言编译的正则。用法和 re.Pattern.search 一样。"""

    def __init__(self, dotted: str) -> None:
        self.dotted = dotted

    def _re(self) -> re.Pattern:
        return compile_intent(current_reply(), self.dotted)

    def search(self, text: str, *args, **kwargs):
        return self._re().search(text or "", *args, **kwargs)

    def match(self, text: str, *args, **kwargs):
        return self._re().match(text or "", *args, **kwargs)

    def fullmatch(self, text: str, *args, **kwargs):
        return self._re().fullmatch(text or "", *args, **kwargs)

    def sub(self, repl: str, text: str, *args, **kwargs) -> str:
        return self._re().sub(repl, text or "", *args, **kwargs)


def role_stop() -> set:
    raw = _dig(intents(), "roleplay.role_stop") or []
    return set(raw)


def role_bad_head() -> str:
    raw = _dig(intents(), "roleplay.role_bad_head")
    return raw if isinstance(raw, str) else ""


def _volc_lang(voice: str) -> str:
    vid = (voice or "").strip()
    low = vid.lower()
    if low.startswith("zh_") or "_zh_" in low:
        return "zh-CN"
    if low.startswith("en_") or "_en_" in low:
        return "en"
    if low.startswith("ja_") or "_ja_" in low:
        return "ja"
    if low.startswith("ko_") or "_ko_" in low:
        return "ko"
    return ""


def voice_lang(engine: str, voice: str) -> str:
    vid = (voice or "").strip()
    eng = (engine or "").strip().lower()
    if eng == "volc":
        return _volc_lang(vid)
    if eng == "qwen" or vid in _QWEN_LANG:
        return _QWEN_LANG.get(vid, "")
    if vid.startswith("zh-"):
        return "zh-CN"
    if vid.startswith("en-"):
        return "en"
    if vid.startswith("ja-"):
        return "ja"
    if vid.startswith("ko-"):
        return "ko"
    return ""


def default_voice(engine: str, lang: str | None) -> str:
    lang = normalize(lang)
    eng = (engine or "").strip().lower()
    if eng == "qwen":
        return QWEN_DEFAULT.get(lang, "Serena")
    if eng == "volc":
        return VOLC_DEFAULT.get(lang, "zh_female_vv_uranus_bigtts")
    if eng == "openai":
        return "marin"
    if eng == "eleven":
        return "21m00Tcm4TlvDq8ikWAM"
    if eng == "gemini":
        return "Kore"
    return EDGE_DEFAULT.get(lang, "zh-CN-XiaoyiNeural")


def voice_fits(engine: str, voice: str, lang: str | None) -> bool:
    """这个音色能不能拿来念该对话语言。英语允许塞蕾娜 / 薇薇安，避免落到男声。"""
    lang = normalize(lang)
    vid = (voice or "").strip()
    have = voice_lang(engine, vid)
    if have == lang:
        return True
    eng = (engine or "").strip().lower()
    return lang == "en" and eng == "qwen" and vid in _QWEN_EN_FEMALE


def align_voice(engine: str, voice: str, lang: str | None) -> str:
    """音色对不上对话语言时，落到该语言的默认音色。英语默认是女声。"""
    lang = normalize(lang)
    vid = (voice or "").strip()
    if not vid:
        return default_voice(engine, lang)
    if voice_fits(engine, vid, lang):
        return vid
    if not voice_lang(engine, vid):
        if (engine or "").strip().lower() == "volc" and "uranus" not in vid and not vid.startswith("ICL_"):
            return default_voice(engine, lang)
        return vid
    return default_voice(engine, lang)


def tod_index(hour: int) -> int:
    if hour < 5:
        return 0
    if hour < 9:
        return 1
    if hour < 12:
        return 2
    if hour < 14:
        return 3
    if hour < 18:
        return 4
    if hour < 23:
        return 5
    return 6
