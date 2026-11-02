"""Optional native Windows OCR. Screen words never become instructions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import hashlib
import threading
import time
from collections import OrderedDict
from copy import deepcopy
import importlib.util
import logging
from functools import lru_cache
from difflib import SequenceMatcher


@lru_cache(maxsize=1)
def champions() -> dict:
    try:
        return json.loads(Path(__file__).with_name("league_names.json").read_text(encoding="utf-8"))["champions"]
    except (OSError, ValueError, KeyError):
        return {}


def hero_name(raw: str) -> str:
    normalized = re.sub(r"\s+", "", raw).lower()
    for ident, item in champions().items():
        if normalized in {re.sub(r"\s+", "", alias).lower() for alias in (ident, item["name"], item["title"])}:
            return item["title"]
    return raw


def hero_mentions(text: str) -> list[dict[str, str]]:
    """Resolve names, titles and champion IDs; a mention does not prove ownership."""
    compact = re.sub(r"\s+", "", text)
    found = []
    for ident, item in champions().items():
        for alias in (item["title"], item["name"], ident):
            alias = re.sub(r"\s+", "", alias)
            if re.fullmatch(r"[A-Za-z0-9]+", alias):
                matched = re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", compact, re.I)
            elif len(alias) == 1:
                matched = re.search(r"(?<![\u4e00-\u9fff])" + re.escape(alias) + r"(?![\u4e00-\u9fff])", text)
            else:
                matched = alias in compact
            if matched:
                found.append({"id": ident, "hero": item["title"], "alias": alias})
                break
    return found


def owned_selection(text: str) -> str:
    """Only explicit ownership, not a hover, search result, teammate or ban."""
    compact = re.sub(r"\s+", "", text)
    if re.search(r"队友|敌方|对方|对面|禁用|封禁|推荐|搜索|悬停|预选|未锁定|没有锁定|尚未锁定", compact):
        return ""
    if not re.match(r"^(?:你的英雄[:：]|您选择的英雄[:：]|玩家英雄[:：]|当前使用的英雄[:：]|(?:你|我|已)已?锁定[:：]?)", compact):
        return ""
    mentions = hero_mentions(text)
    return mentions[0]["hero"] if len(mentions) == 1 else ""


def verify(text: str, lines: list[dict]) -> str:
    """Keep model actions; transcribed text must agree with independent OCR."""
    if not lines:
        return text
    normalize = lambda value: re.sub(r"[^\w\u4e00-\u9fff]", "", value).lower()
    originals = [(str(line.get("text") or ""), normalize(str(line.get("text") or ""))) for line in lines]
    kept = []
    for row in text.splitlines():
        if not re.match(r"^\s*[-*]?\s*原文[:：]", row):
            kept.append(row)
            continue
        value = normalize(re.split(r"[:：]", row, maxsplit=1)[-1])
        matched = max(originals, key=lambda pair: SequenceMatcher(None, value, pair[1]).ratio())
        if len(value) >= 3 and SequenceMatcher(None, value, matched[1]).ratio() >= 0.72:
            kept.append("原文：" + " ".join(matched[0].split())[:90])
    return "\n".join(kept)


_ocr_cache: OrderedDict = OrderedDict()
_ocr_cache_lock = threading.Lock()
_rapid_reader = None
_rapid_retry_at = 0.0
_rapid_error = ""
_rapid_lock = threading.Lock()


def _read_backend(image) -> list[dict]:
    global _rapid_reader, _rapid_retry_at, _rapid_error
    if os.environ.get("XIAOKE_OCR_ENGINE", "rapidocr").lower() == "windows":
        return _read_native(image)
    if time.monotonic() >= _rapid_retry_at:
        try:
            with _rapid_lock:
                if _rapid_reader is None:
                    spec = importlib.util.spec_from_file_location("_xiaoke_rapid_text", Path(__file__).with_name("rapid_text.py"))
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    _rapid_reader = module
            rows = _rapid_reader.read(image)
            _rapid_error = ""
            return rows
        except Exception as exc:
            _rapid_error = f"{type(exc).__name__}: {exc}"[:240]
            _rapid_retry_at = time.monotonic() + 30
            logging.getLogger(__name__).warning("RapidOCR unavailable; using Windows OCR: %s", _rapid_error)
    return _read_native(image)


def read(image) -> list[dict]:
    """Reuse exact pixels only; a changing subtitle or timer always gets a new read."""
    key = (os.environ.get("XIAOKE_OCR_ENGINE", "rapidocr"), image.mode, image.size, hashlib.blake2b(image.tobytes(), digest_size=16).digest())
    now = time.monotonic()
    with _ocr_cache_lock:
        cached = _ocr_cache.get(key)
        if cached and now - cached[0] < 30:
            _ocr_cache.move_to_end(key)
            return deepcopy(cached[1])
    rows = _read_backend(image)
    if rows:
        with _ocr_cache_lock:
            _ocr_cache[key] = (time.monotonic(), deepcopy(rows))
            _ocr_cache.move_to_end(key)
            while len(_ocr_cache) > 4:
                _ocr_cache.popitem(last=False)
    return rows


def _read_native(image) -> list[dict]:
    if os.name != "nt":
        return []
    name = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            name = handle.name
        image.save(name)
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(Path(__file__).with_name("read_screen.ps1")), "-ImagePath", name],
            capture_output=True, timeout=12, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            return []
        rows = json.loads(result.stdout.decode("utf-8-sig"))
        rows = rows if isinstance(rows, list) else [rows]
        for row in rows:
            row["engine"] = "windows"
        return rows
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    finally:
        if name:
            Path(name).unlink(missing_ok=True)


def facts(lines: list[dict], *, image_size: tuple[int, int] | None = None) -> str:
    """Only small, verifiable game labels. Never forward chat text or the whole UI."""
    result: list[str] = []
    aliases = champions()
    visible: set[str] = set()
    bots: set[str] = set()
    owned: list[str] = []
    owned_lines: dict[str, str] = {}
    hero_lines: dict[str, str] = {}
    bot_positions: list[tuple[float, float]] = []
    human_positions: dict[str, tuple[float, float]] = {}
    for line in lines:
        raw = str(line.get("text") or "")
        compact = re.sub(r"\s+", "", raw)
        mentions = hero_mentions(raw)
        for mention in mentions:
            visible.add(mention["id"])
            hero_lines[mention["hero"]] = compact
            words = line.get("words") or []
            position = (float(words[0].get("x", 0)), float(words[0].get("y", 0))) if words else None
            if "电脑" in compact:
                bots.add(mention["id"])
                if position:
                    bot_positions.append(position)
            elif position:
                human_positions[mention["id"]] = position
        selected = owned_selection(raw)
        if selected:
            owned.append(selected)
            owned_lines[selected] = compact
        if "陪看记录" in compact:
            return "仍在：否\n画面：陪看记录"
        if re.search(r"VLESS|订阅设置|系统代理|服务器地址", compact, re.I):
            return "仍在：否\n画面：非游戏窗口"
        if re.fullmatch(r"胜利|失败|VICTORY|DEFEAT", compact, re.I):
            result.append("结果：" + ("胜利" if compact.upper() in {"胜利", "VICTORY"} else "失败"))
        countdown = re.search(r"返回于\s*(\d+)", compact)
        if countdown:
            result.append(f"原文：返回于 {countdown.group(1)}")
        elif compact == "返回于" and line.get("words"):
            # RapidOCR can split the label and its number into adjacent rows.
            word = line["words"][0]
            center = float(word.get("x", 0)) + float(word.get("width", 0))/2
            y = float(word.get("y", 0))
            height = max(1, float(word.get("height", 0)))
            nearby = []
            for candidate in lines:
                number = re.sub(r"\s+", "", str(candidate.get("text") or ""))
                if not re.fullmatch(r"\d{1,3}", number) or not candidate.get("words"):
                    continue
                box = candidate["words"][0]
                cx = float(box.get("x", 0)) + float(box.get("width", 0))/2
                dy = float(box.get("y", 0)) - y
                if 0 < dy < height*4 and abs(cx-center) < max(20, height*2):
                    nearby.append((dy, number))
            if nearby:
                result.append("原文：返回于 " + min(nearby)[1])
        if re.search(r"^\d+vs\d+$|^\d{1,2}:\d{2}$", compact, re.I):
            result.append("局面：局内HUD可见")
        if "所有物品" in compact or "装备商店" in compact:
            result.append("画面：装备商店打开了")
        # Preserve the exact loading-card line as text, not a guessed player identity.
        if mentions or re.search(r"选择你的英雄|等待复活|正在寻找对局|继续游戏", compact):
            result.append("原文：" + compact[:70])
    if visible:
        names = [aliases[ident]["title"] for ident in sorted(visible)]
        result.append("可见英雄：" + "、".join(names[:12]))
    if len(set(owned)) == 1:
        hero = owned[0]
        if any("锁定" in line.get("text", "") or "选择你的英雄" in line.get("text", "") for line in lines):
            result.append("阶段：选英雄")
        result += [f"英雄：{hero}", "英雄依据：屏幕明确写出玩家归属或锁定", "身份来源：ocr",
                   "原文：" + owned_lines[hero]]
        return "\n".join(result)
    # In practice-tool/bot loading screens, an explicitly labelled computer is
    # not the local player. Never infer ownership from card size or position.
    humans = visible - bots
    loading_layout = True
    if image_size:
        width, height = image_size
        positions = [p for p in bot_positions if p[1] > height * .6]
        human = human_positions.get(next(iter(humans))) if len(humans) == 1 else None
        loading_layout = bool(human and human[1] < height * .55 and len(positions) >= 2
                              and max(p[0] for p in positions) - min(p[0] for p in positions) > width * .12)
    if len(visible) >= 2 and bots and len(humans) == 1 and loading_layout:
        hero = aliases[next(iter(humans))]["title"]
        result += ["阶段：进入对局", f"英雄：{hero}", "英雄依据：加载卡中唯一未标记电脑的玩家", "身份来源：ocr",
                   "原文：" + hero_lines[hero]]
    return "\n".join(result)
