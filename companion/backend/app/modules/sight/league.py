"""LoL evidence rules. Player identity is distinct from the camera target."""
from __future__ import annotations

import re

UNKNOWN = {"", "空", "无", "没有", "未知", "没看清", "没变", "是", "否"}


def clean_slots(slots: dict[str, str]) -> dict[str, str]:
    """A copied instruction is not an observation."""
    echoes = ("玩家自己的英雄", "有把握才写", "明确看见才写", "认不准", "没变留空", "已购买的装备", "一行屏幕原字", "最后一张正在发生", "较早帧发生", "悬停和推荐不算")
    cleaned = {k: v for k, v in slots.items() if not any(x in v for x in echoes)}
    hero = cleaned.get("英雄", "")
    if hero:
        from .screen_text import champions

        known = {x for ident, item in champions().items() for x in (ident.lower(), item["name"], item["title"])}
        if hero.lower() not in known:
            cleaned.pop("英雄", None)
    return cleaned


def positive_text(text: str) -> str:
    # A negated or hypothetical clause is not evidence, even when it names a result.
    clauses = re.split(r"[，,。；;\n]", text)
    return "，".join(c for c in clauses if not re.search(
        r"没有|没出现|未出现|尚未|还没|不是|并非|看不到|看不清|未见|如果|假如|可能|不要|是否|不确定", c
    ))


def evidence(slots: dict[str, str]) -> str:
    return positive_text("\n".join(
        value for key, value in slots.items()
        if key in {"画面", "原文", "结果", "局面"} or re.fullmatch(r"第\d+张", key)
    ))


def result(text: str) -> str:
    found = positive_text(text)
    win = bool(re.search(r"胜利|\bVICTORY\b", found, re.I))
    lose = bool(re.search(r"失败|\bDEFEAT\b", found, re.I))
    return "胜利" if win and not lose else "失败" if lose and not win else ""


def phase(slots: dict[str, str], current: str) -> str:
    """Independent screen states, not an ordered progression through combat."""
    text = evidence(slots)
    named = slots.get("阶段", "")
    if re.search(r"陪看记录|网络流量统计|游戏设置窗口|非游戏窗口|VLESS|://|\.com:\d+", text, re.I):
        return ""
    if named == "load" and slots.get("身份来源") == "ocr":
        return "load"
    if result(text) and current not in {"launch", "lobby", "party", "queue", "select"}:
        return "score"
    if "继续游戏" in text and current in {"load", "lane", "fight", "dead", "shop", "leave", "score"}:
        return "score"
    rules = (
        ("dead", r"返回于\s*\d+|等待复活|复活倒计时|画面变灰|已经阵亡|被击杀|阵亡了"),
        ("select", r"选择你的英雄|锁定英雄|禁用英雄"),
        ("queue", r"正在寻找对局|接受对局|匹配队列"),
        ("party", r"队友格子|邀请玩家|组队房间"),
        ("load", r"加载界面|加载画面|加载进度|英雄立绘|立绘卡片"),
        ("shop", r"商店.*打开|打开.*商店|装备商店|商店格子|正在购买|装备配置弹窗"),
        ("leave", r"准备出门|走出泉水|离开泉水|已经复活.*泉水"),
        ("fight", r"团战|多个英雄.*交战|好几个英雄.*放技能|打起来了"),
        ("lane", r"小兵|兵线|清兵|补刀|对线|已经复活|回到线上|河道|泉水|野区|防御塔|施法|释放技能|血条|峡谷|增加金钱|局内HUD"),
        ("lobby", r"游戏大厅|英雄联盟大厅|模式入口|主页.*PLAY"),
    )
    for pid, pattern in rules:
        if current in {"launch", "lobby", "party", "queue", "select"} and pid in {"lane", "fight", "dead", "shop", "leave"}:
            continue
        if re.search(pattern, text, re.I):
            return pid
    if named == "select" and slots.get("英雄", "").strip() not in UNKNOWN:
        return "select"
    # Named phase needs real evidence, and cannot settle victory or death by itself.
    if named in {"lane", "fight", "shop", "leave"} and text and current not in {"launch", "lobby", "party", "queue", "select"}:
        return named
    if text and current in {"shop", "leave", "fight", "dead"}:
        # A temporary state needs fresh evidence in every observation. Falling
        # back to general play does not assert revival, a lane, or a purchase.
        return "lane"
    return current if text or any(
        slots.get(k, "").strip() not in UNKNOWN for k in ("英雄", "局面", "装备", "线路", "分路")
    ) else ""


def ttl(phase_id: str) -> float:
    return {"fight": 8.0, "dead": 6.0, "lane": 12.0, "score": 90.0}.get(phase_id, 30.0)


def observation_timing(previous: str, text: str, age: float) -> dict[str, str]:
    # A cached death state must not discard a living frame before parsing it.
    incoming = phase({"画面": text}, previous) or previous
    return {"freshness_phase": incoming, "capture_age": str(round(age, 3)), "freshness_limit": str(ttl(incoming))}


def prompt() -> str:
    return (
        "只看最后一张英雄联盟截图。用两行写真实看见的内容，不要复述问题。"
        "第一行用「画面：」开头，描述此刻的具体动作。"
        "第二行用「原文：」开头，照抄一行关键文字。没有字就省略第二行。"
        "不知道就写没变，不猜英雄名字，不说心情。"
    )


def detailed_prompt() -> str:
    return (
        "你在看英雄联盟。多张图按时间从早到晚。描述最后一张的当前状态；"
        "较早的动作写在刚才一栏，不能当成此刻还在发生。只写看见的事实，不猜。\n"
        "阶段可写：大厅、组队、排队、选英雄、进入对局、出装、出门、对线、团战、阵亡、结算。"
        "阶段不要求按顺序走；认不准留空。\n"
        "玩家英雄从已锁定的选择、加载卡的玩家标识、自己的HUD确认。"
        "镜头正中、队友、敌人、选中单位不等于玩家本人。名字认不准留空。"
        "不要用某一种加载卡排版猜自己是谁。\n"
        "原文只照抄能读到的关键字。没有胜负就不要写胜利、失败。"
        "陪看记录页、桌面、设置页不算游戏动作。\n"
        "画面：最后一张正在发生的动作，一句\n原文：关键提示原字\n"
        "阶段：\n英雄：玩家自己的英雄\n英雄依据：玩家标识或HUD原字，认不准空着\n"
        "镜头英雄：\n局面：新变化，没变留空\n装备：已购买的装备，悬停和推荐不算\n"
        "线路：有把握才写\n结果：明确看见才写\n刚才：较早帧发生而现在已结束的动作\n"
        "仍在：是或否。没有新的事实只写没变。"
    )
