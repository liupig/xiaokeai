"""用户插话分流：正在跳 / 正在说时，新文本是附和、先记下，还是立刻开新一轮。"""
from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional

from . import llm as llm_service

Busy = Literal["dance", "speech", "generate"]
Act = Literal["drop", "hold", "cut"]

_CUT = re.compile(
    r"停(下|一下|止)?|别说了|别跳|不要跳|别唱|闭嘴|换(一)?支|换(一)?个|换个故事|跳别的|"
    r"再来(一)?(支|首|个)|过来|听我说|坐下|站起来|往左|往右"
)
_ASK = re.compile(r"[？?]|为什么|怎么(办|了|样)?|什么意思|叫什么|哪支|哪首|几点")
_DROP = re.compile(
    r"真好|好看|好漂亮|好美|好帅|好厉害|太棒|太美|爱了|牛逼?|666|"
    r"跳[得的]?真好|跳[得的]?好看|舞跳得好|不错|加油"
)
_BACK = re.compile(
    r"^(嗯+|啊+|哦+|噢+|额+|唔+|哈+|嘿+|哇+|好|对|是|可以|行|继续|是的|对对)"
    r"[啊呀哦噢哈嗯！!。.~～…]*$"
)
_HOLD_TAIL = re.compile(r"(那个|就是|然后|还有|对了|我想想|就是说)$")
_HOLD_HEAD = re.compile(r"^(那个|就是|然后|还有|对了|我想)")
_SPACE = re.compile(r"\s+")

INGRESS_HINT = """你在判断：角色正忙时，用户插进来一句。只输出 JSON：{"act":"drop|hold|cut"}
busy=dance 正在跳舞；speech 正在说话；generate 正在生成回复。
drop：附和、夸奖、嗯啊，不需要停，也不必回答。例：跳舞时「跳的真好」「好看」「加油」。
hold：有点内容，但可以等这支舞/这句话说完再答。例：半句「那个我觉得」、补充一句不急的话。
cut：新意图，必须马上停。例：提问、点播/换舞、制止、叫名字办事、换话题。
不确定：dance 用 drop，speech/generate 用 cut。不要解释。"""


def _norm(text: str) -> str:
    return _SPACE.sub("", (text or "")).strip()


def local_act(text: str, busy: Busy) -> Optional[Act]:
    t = _norm(text)
    if not t:
        return "drop"
    # 喇叭回声常被听成 OkayOkay / The. / Yeah.，不当插话
    if len(t) <= 16 and not re.search(r"[\u4e00-\u9fff]", t):
        return "drop"
    if _CUT.search(t) or _ASK.search(t):
        return "cut"
    if _BACK.match(t) or _DROP.search(t):
        return "drop"
    if len(t) <= 2:
        return "drop" if busy == "dance" else "hold"
    if (_HOLD_HEAD.match(t) or _HOLD_TAIL.search(t)) and len(t) <= 8:
        return "hold"
    if busy in ("speech", "generate"):
        return "cut"
    return None


def fallback_act(busy: Busy) -> Act:
    return "drop" if busy == "dance" else "cut"


def _parse_act(blob: Any) -> Optional[Act]:
    if not isinstance(blob, dict):
        return None
    act = str(blob.get("act") or "").strip().lower()
    return act if act in ("drop", "hold", "cut") else None


async def decide(
    llm_conf: Dict[str, Any],
    *,
    text: str,
    busy: Busy,
    last_user: str = "",
    last_assistant: str = "",
) -> Act:
    hit = local_act(text, busy)
    if hit:
        return hit
    conf = dict(llm_conf or {})
    if not (conf.get("api_key") or "").strip():
        return fallback_act(busy)
    conf["temperature"] = 0.1
    conf["thinking"] = "off"
    conf["max_tokens"] = 48
    user = (
        f"busy={busy}\n用户这句：{(text or '')[:120]}\n"
        f"上一轮用户：{(last_user or '')[:80]}\n"
        f"上一轮角色：{(last_assistant or '')[:80]}"
    )
    blob = await llm_service.complete_json(
        conf,
        [{"role": "system", "content": INGRESS_HINT}, {"role": "user", "content": user}],
        max_tokens=48,
        timeout=4,
    )
    return _parse_act(blob) or fallback_act(busy)
