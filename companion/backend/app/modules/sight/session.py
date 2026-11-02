"""体验锁。这一眼用已经锁住的规格；这一眼的结果只决定下一眼加载哪一套。"""
from __future__ import annotations

import re
import threading
import time

from . import catalog
from .brief import make_brief
from .match import match
from .model import Brief, Order, Sub

_MISS_LIMIT = 2
_lock = threading.Lock()
_kind = ""
_sub = ""
_phase = ""
_held = False
_misses = 0
_switch_kind = ""
_switch_sub = ""
_switch_hits = 0
_facts: dict[str, str] = {}
_surface = ""
_fact_time = 0.0


def reset() -> None:
    global _kind, _sub, _phase, _held, _misses, _switch_kind, _switch_sub, _switch_hits, _facts, _surface
    with _lock:
        _kind = ""
        _sub = ""
        _phase = ""
        _held = False
        _misses = 0
        _switch_kind = ""
        _switch_sub = ""
        _switch_hits = 0
        _facts = {}
        _surface = ""


def hold(kind_id: str, sub_id: str) -> bool:
    """点名打开时立刻锁上，第一眼就用正在打开的规格。"""
    global _kind, _sub, _phase, _held, _misses, _switch_hits, _facts, _surface
    sub = catalog.find_sub(kind_id, sub_id)
    if sub is None:
        return False
    with _lock:
        _kind = sub.kind
        _sub = sub.id
        _phase = sub.phases[0].id
        _held = True
        _misses = 0
        _switch_hits = 0
        _facts = {}
        _surface = "client"
        _clear_switch()
    return True


def release() -> None:
    reset()


def prepare(process: str = "", title: str = "", window: str = "") -> Order:
    del process, title, window
    with _lock:
        sub = catalog.find_sub(_kind, _sub)
        if sub is None:
            return Order()
        phase = sub.phase(_phase) or sub.phases[0]
        kind = catalog.kind_of(sub.kind)
        return Order(
            active=True,
            kind=sub.kind,
            sub=sub.id,
            phase=phase.id,
            scene=sub.scene,
            prompt=catalog.prompt_for(sub, phase, _surface),
            frames=phase.frames,
            detail=phase.detail or sub.id == "league",
            interval=(3.0 if phase.id in {"lane", "fight", "dead"} else 6.0) if sub.id == "league" else kind.interval if kind else 0,
        )


def commit(process: str, title: str, window: str, eyes_text: str) -> Brief:
    hit = match(process, title, window)
    with _lock:
        _apply(hit, eyes_text)
        sub = catalog.find_sub(_kind, _sub)
        if sub is None:
            return Brief()
        phase = sub.phase(_phase) or sub.phases[0]
        _slots_now, left = _slots(eyes_text, sub)
        if left and not _still_here(hit, sub):
            _drop()
            return Brief()
        return make_brief(sub, phase, _facts, _surface)


def current() -> Brief:
    with _lock:
        sub = catalog.find_sub(_kind, _sub)
        if sub is None:
            return Brief()
        phase = sub.phase(_phase) or sub.phases[0]
        facts = _facts
        if sub.id == "league":
            from .league import ttl

            if time.time() - _fact_time > ttl(phase.id):
                facts = {k: v for k, v in _facts.items() if k in {"英雄", "线路", "分路"}}
        return make_brief(sub, phase, facts, _surface)


def snapshot() -> dict:
    with _lock:
        return {
            "kind": _kind,
            "sub": _sub,
            "phase": _phase,
            "held": _held,
            "surface": _surface,
        }


def _apply(hit, eyes_text: str) -> None:
    global _kind, _sub, _phase, _misses, _switch_kind, _switch_sub, _switch_hits
    sub = catalog.find_sub(_kind, _sub)
    if sub is None:
        if hit is None:
            return
        _lock_hit(hit)
        sub = catalog.find_sub(_kind, _sub)
        if sub is None:
            return
        slots, left = _read_slots(eyes_text, sub)
        if left and not _still_here(hit, sub):
            _drop()
            return
        _remember(sub, slots)
        return
    slots, left = _read_slots(eyes_text, sub)
    if left and not _still_here(hit, sub):
        _drop()
        return
    here = _still_here(hit, sub)
    if here:
        _remember(sub, slots)
    if here and not _phase_id(slots.get("阶段", ""), sub) and hit is not None and hit.phase_hint:
        _advance(sub, hit.phase_hint)
    if here:
        _misses = 0
        if hit.surface:
            _set_surface(hit.surface)
        _clear_switch()
        return
    if hit is not None:
        if hit.kind == _switch_kind and hit.sub == _switch_sub:
            _switch_hits += 1
        else:
            _switch_kind = hit.kind
            _switch_sub = hit.sub
            _switch_hits = 1
        if _switch_hits >= _MISS_LIMIT:
            _lock_hit(hit)
        return
    _clear_switch()
    opening = _phase == sub.phases[0].id
    if _held and opening:
        return
    _misses += 1
    if _misses >= _MISS_LIMIT:
        _drop()


def _still_here(hit, sub: Sub) -> bool:
    """进程还是这个软件时，模型写的「仍在：否」不算离开。"""
    return hit is not None and hit.kind == sub.kind and hit.sub == sub.id


def _lock_hit(hit) -> None:
    global _kind, _sub, _phase, _misses, _facts
    sub = catalog.find_sub(hit.kind, hit.sub)
    if sub is None:
        return
    _kind = sub.kind
    _sub = sub.id
    _phase = _entry_phase(sub, hit.phase_hint)
    _misses = 0
    _facts = {}
    _set_surface(hit.surface)
    _clear_switch()


def _entry_phase(sub: Sub, hint: str) -> str:
    if hint and sub.phase(hint) is not None:
        return hint
    return sub.phases[0].id


def _advance(sub: Sub, hint: str) -> None:
    """进程只能把阶段往开局方向推一步，不能把对线拉回大厅。"""
    global _phase
    if sub.phase(hint) is None:
        return
    if not _phase:
        _phase = hint
        return
    if _index(sub, _phase) < _index(sub, hint):
        _phase = hint


def _index(sub: Sub, phase_id: str) -> int:
    for i, phase in enumerate(sub.phases):
        if phase.id == phase_id:
            return i
    return -1


def _phase_id(text: str, sub: Sub) -> str:
    raw = (text or "").strip().strip("。！!？?….\"'“” ")
    raw = raw.split("。")[0].split("，")[0].split(",")[0].split(" ")[0].strip()
    if not raw:
        return ""
    if sub.id == "league" and raw == "对线":
        return "lane"
    for phase in sub.phases:
        if raw == phase.id or raw == phase.label:
            return phase.id
    return ""


def _watching_lab(text: str) -> bool:
    return "陪看记录" in (text or "")


def _read_slots(text: str, sub: Sub) -> tuple[dict[str, str], bool]:
    """陪看记录页上的字不是这一局的画面。"""
    if _watching_lab(text):
        return {}, False
    slots, left = _slots(text, sub)
    if sub.kind in {"movie", "music", "video"}:
        from .media import normalize

        slots = normalize(text, slots)
    if sub.id == "league":
        from .league import clean_slots

        slots = clean_slots({key.lstrip("- *0123456789.、"): value for key, value in slots.items()})
        frames = sorted((int(m.group(1)), value) for key, value in slots.items()
                        if (m := re.fullmatch(r"第(\d+)张", key)))
        meaningful = [(n, v) for n, v in frames if not any(word in v for word in _DULL)]
        if meaningful:
            # Older frames are history, never evidence of the current phase.
            slots = {"画面": meaningful[-1][1]}
            if len(meaningful) > 1:
                slots["刚才"] = "；".join(v for _, v in meaningful[:-1]
                                         if not re.search(r"设置|网络|窗口|陪看记录|统计", v))[-160:]
    return slots, left


def _slots(text: str, sub: Sub) -> tuple[dict[str, str], bool]:
    found: dict[str, str] = {}
    for line in (text or "").splitlines():
        if "：" in line:
            key, value = line.split("：", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = key.strip()
        value = value.strip()
        if key:
            if key in {"原文", "画面", "字幕", "歌词"} and found.get(key) and value != found[key]:
                found[key] = (found[key] + "；" + value)[:600]
            else:
                found[key] = value
    left = found.get("仍在", "") in {"否", "不", "不是", "离开", "没了"}
    named = _phase_id(found.get("阶段", ""), sub)
    if not named and "阶段" not in found:
        yes = []
        for key, value in found.items():
            label = _phase_id(key, sub)
            mark = value.strip().strip("。！!？?….\"'“” ")
            mark = mark.split("，")[0].split(",")[0].split(" ")[0]
            if label and mark in {"是", "对", "yes"} and label not in yes:
                yes.append(label)
        if len(yes) == 1:
            named = yes[0]
    if named:
        found["阶段"] = named
    else:
        bare = []
        for line in (text or "").splitlines():
            label = _phase_id(line, sub)
            if label and label not in bare:
                bare.append(label)
        if len(bare) == 1:
            found["阶段"] = bare[0]
            found["\x00loose"] = "1"
    return found, left


_SKIP = (
    "也没有", "没有", "写着", "出现", "弹出", "标题", "中间", "正在",
    "可以", "点的", "一圈", "一排", "左边", "旁边", "画面", "一个",
    "好几个", "几个", "还是", "不是",
)
_GENERIC = {"英雄", "模式", "现在", "这个", "已经", "打开", "选择", "你的", "一起"}
_NO = {"是", "否", "对", "yes", "不", "不是"}


def _remember(sub: Sub, slots: dict[str, str]) -> None:
    """阶段跟着画面上的字走。只复述阶段名字，不算看见了。"""
    global _phase, _facts, _fact_time
    slots.pop("\x00loose", "")
    phase = sub.phase(_phase)
    if phase is None:
        return
    if sub.kind in {"movie", "music", "video"}:
        from .media import update

        _phase, _facts = update(sub, _phase, _facts, slots)
        _fact_time = time.time()
        return
    picked = _accept(sub, phase, slots)
    if not picked:
        return
    previous = _phase
    if picked != _phase:
        carried = {key: value for key, value in _facts.items() if key in {"英雄", "线路", "分路", "对局时钟"} and value}
        _facts = carried
        _phase = picked
    if sub.id == "league":
        stable = {k: v for k, v in _facts.items() if k in {"英雄", "线路", "分路", "对局时钟"}}
        if slots.get("身份来源") == "liveclient" and "对局时钟" in slots:
            try:
                if float(slots["对局时钟"]) + 20 < float(_facts.get("对局时钟", "0")):
                    stable = {}
                    if _phase == "score":
                        _phase = "lane"
            except ValueError:
                pass
        if picked in {"lobby", "party", "queue", "select"} and previous in {"load", "lane", "fight", "dead", "shop", "leave", "score"}:
            stable = {}
        if picked in {"lobby", "select", "load"} and previous in {"score", "lobby", "select"} and picked != previous:
            stable = {}
        _facts = stable
        _fact_time = time.time()
    for key, value in slots.items():
        if key in {"阶段", "仍在"}:
            continue
        raw = value.strip()
        if sub.id == "league" and key == "英雄":
            from .screen_text import hero_name

            raw = hero_name(raw)
        if not raw or raw in _NO or _phase_id(raw, sub):
            continue
        if sub.id == "league":
            from .league import UNKNOWN

            if raw in UNKNOWN:
                continue
            if key == "英雄" and _facts.get("英雄") and raw != _facts["英雄"]:
                # Camera movements must never change the player's identity mid-match.
                confirmed_select = slots.get("身份来源") == "ocr" and picked == "select" and previous in {"lobby", "party", "queue", "select"}
                if slots.get("身份来源") != "liveclient" and not confirmed_select:
                    continue
        _facts[key] = raw
    if (slots.get("画面") or slots.get("原文") or "").strip():
        for key in ("局面", "装备"):
            if key not in slots:
                _facts.pop(key, None)
    _promote_caption(sub, slots)
    _keep_result(sub)


_DULL = ("没变", "一切静止", "什么都没有发生", "没有任何变化", "没有人和字", "什么都没有")


def _promote_caption(sub: Sub, slots: dict[str, str]) -> None:
    """眼睛若按「第几张」写，把最后一张有内容的说明收成她能接的原文。"""
    if (slots.get("原文") or "").strip() or (slots.get("画面") or "").strip():
        return
    phase = sub.phase(_phase)
    labels = {catalog.slot_label(slot) for slot in phase.slots} if phase is not None else set()
    best = ""
    rank = (-1, -1)
    framed = False
    for key, value in slots.items():
        raw = (value or "").strip()
        if not raw or raw in _NO or key in {"阶段", "仍在"} or key in labels:
            continue
        if _phase_id(raw, sub):
            continue
        if any(word in raw for word in _DULL) and len(raw) <= 16:
            continue
        match = re.fullmatch(r"第(\d+)张", key)
        if not match:
            continue
        framed = True
        number = int(match.group(1))
        score = (1 if _useful_line(sub, raw) else 0, number)
        if score > rank or (score == rank and len(raw) > len(best)):
            best, rank = raw[:80], score
    if framed and best:
        _facts["原文"] = best


def _useful_line(sub: Sub, raw: str) -> bool:
    """后一张如果只是设置窗口，不要盖住前面那张团战或胜利。"""
    phase = sub.phase(_phase)
    if phase is None:
        return False
    ids = _visible_phases(sub, phase)
    ids.add(phase.id)
    for pid in ids:
        item = sub.phase(pid)
        if item and _marked(item.mark, raw):
            return True
    return False


def _keep_result(sub: Sub) -> None:
    """胜利、失败写在任意一行里也算结果，不要只认「结果：」这一格。"""
    phase = sub.phase(_phase)
    if phase is None or "result" not in phase.slots:
        return
    blob = "".join(_facts.values())
    if sub.id == "league":
        from .league import result

        found = result(blob)
    else:
        found = "胜利" if "胜利" in blob else "失败" if "失败" in blob else ""
    if not found:
        return
    current = (_facts.get("结果") or "").strip()
    if current in {"", "空", "无", "没有", "没看清", "未知"}:
        _facts["结果"] = found
    if _facts.get("原文") or _facts.get("画面"):
        return
    for value in _facts.values():
        if found in value and value != found:
            _facts["原文"] = value[:80]
            return


def _blob(slots: dict[str, str]) -> str:
    parts = []
    for key, value in slots.items():
        if key in {"阶段", "仍在"}:
            continue
        raw = (value or "").strip()
        if not raw or raw in _NO:
            continue
        parts.append(raw)
    return " ".join(parts)


def _clues(mark: str) -> list[str]:
    """阶段记号里真正能在画面上读到的词。写在「没有」后面的，是这屏不该有的东西。"""
    text = (mark or "").split("没有")[0]
    for word in _SKIP:
        text = text.replace(word, " ")
    for word in ("的", "或", "和", "与"):
        text = text.replace(word, " ")
    parts = re.findall(r"[A-Za-z]{2,}|[\u4e00-\u9fff]{2,}", text)
    return [part for part in parts if part not in _GENERIC]


def _marked(mark: str, blob: str) -> bool:
    if not mark or not blob:
        return False
    folded = blob.lower()
    return any(clue.lower() in folded for clue in _clues(mark))


def _filled(phase, slots: dict[str, str]) -> bool:
    if phase is None:
        return False
    for slot in phase.slots:
        label = catalog.slot_label(slot)
        raw = (slots.get(label) or slots.get(slot) or "").strip()
        if raw and raw not in _NO and raw not in {"空", "无", "没有", "没看清", "未知"}:
            return True
    return False


def _furthest(sub: Sub, ids: list[str]) -> str:
    return max(ids, key=lambda pid: _index(sub, pid))


def _picture(slots: dict[str, str]) -> bool:
    for key in ("画面", "原文"):
        raw = (slots.get(key) or "").strip()
        if len(raw) >= 2 and raw not in _NO:
            return True
    return False


def _visible_phases(sub: Sub, current) -> set[str]:
    """进了对局之后，复活倒计时和胜利不用等流程走到那一格才认。"""
    allowed = set(catalog.ahead_ids(sub, current))
    load_at = _index(sub, "load")
    if load_at < 0 or _index(sub, current.id) < load_at:
        return allowed
    for phase in sub.phases:
        if _index(sub, phase.id) > _index(sub, current.id):
            allowed.add(phase.id)
    return allowed


def _accept(sub: Sub, current, slots: dict[str, str]) -> str:
    """画面上的字优先于模型报的阶段名。这一屏有新句子，也留下来给她说。"""
    if sub.id == "league":
        from .league import phase

        return phase(slots, current.id)
    blob = _blob(slots)
    hits = [
        pid for pid in _visible_phases(sub, current)
        if pid != current.id and _marked((sub.phase(pid).mark if sub.phase(pid) else ""), blob)
    ]
    if hits:
        return _furthest(sub, hits)
    named = slots.get("阶段") or ""
    ahead = catalog.ahead_ids(sub, current)
    if named in ahead and named != current.id:
        phase = sub.phase(named)
        if _filled(phase, slots) or _marked(phase.mark if phase else "", blob):
            return named
    if _filled(current, slots) or _picture(slots):
        return current.id
    return ""


def _set_surface(surface: str) -> None:
    global _surface
    if surface in {"client", "web"}:
        _surface = surface


def _drop() -> None:
    global _kind, _sub, _phase, _held, _misses, _facts, _surface
    _kind = ""
    _sub = ""
    _phase = ""
    _held = False
    _misses = 0
    _facts = {}
    _surface = ""
    _clear_switch()


def _clear_switch() -> None:
    global _switch_kind, _switch_sub, _switch_hits
    _switch_kind = ""
    _switch_sub = ""
    _switch_hits = 0
