"""直播专用成语接龙。回合由状态机决定，不让模型猜谁说了什么。"""
from __future__ import annotations

import random
import re

_START = re.compile(r"成语接龙")
_STOP = re.compile(r"不玩了|换个游戏|结束游戏")
_TURN = re.compile(r"到你了|该你了|该你接|轮到谁|该谁了")
_IDIOM = re.compile(r"^[\u4e00-\u9fff]{4}$")

# AI 只从确定存在的成语里接，不为延续游戏编造词。
_ANSWERS = {
    "一": ["一心一意", "一帆风顺"], "心": ["心想事成", "心平气和"], "意": ["意气风发", "意味深长"],
    "风": ["风和日丽"], "顺": ["顺水推舟"], "气": ["气壮山河"], "长": ["长年累月"],
    "和": ["和蔼可亲"], "平": ["平易近人"], "静": ["静观其变"], "舟": ["舟车劳顿"],
    "河": ["河东狮吼"], "山": ["山清水秀"], "人": ["人山人海"], "海": ["海阔天空"],
    "空": ["空前绝后"], "后": ["后发制人"], "水": ["水到渠成"], "成": ["成千上万"],
    "万": ["万事如意"], "事": ["事半功倍"], "倍": ["倍加珍惜"], "为": ["为富不仁"],
    "仁": ["仁义道德", "仁者无敌"], "德": ["德才兼备"], "备": ["备而不用"], "用": ["用心良苦"],
    "苦": ["苦口婆心"], "名": ["名副其实"], "实": ["实事求是"], "是": ["是非分明"],
    "分": ["分道扬镳"], "道": ["道听途说"], "说": ["说一不二"], "二": ["二话不说"],
    "话": ["话不投机"], "机": ["机不可失"], "失": ["失而复得"], "得": ["得心应手"],
    "应": ["应有尽有"], "有": ["有条不紊"], "条": ["条理清晰"], "清": ["清清楚楚"],
    "楚": ["楚楚动人"], "动": ["动人心弦"], "师": ["师出有名"], "出": ["出类拔萃"],
    "群": ["群策群力"], "力": ["力所能及"], "及": ["及时行乐"], "乐": ["乐在其中"],
    "中": ["中流砥柱"],
}
_OPENERS = ("一心一意", "一帆风顺", "心想事成", "万事如意")


class IdiomGame:
    def __init__(self) -> None:
        self.active = False
        self.required = ""
        self.last_user = ""
        self.last_nickname = ""
        self.last_ai = ""
        self.used: set[str] = set()

    def clear(self) -> None:
        self.__init__()

    def handles(self, text: str) -> bool:
        raw = str(text or "").strip()
        if _START.search(raw) or (self.active and _STOP.search(raw)):
            return True
        if not self.active:
            return False
        return bool(_IDIOM.fullmatch(raw) or _TURN.search(raw))

    def respond(self, nickname: str, text: str) -> str:
        raw = str(text or "").strip()
        who = nickname or "这位朋友"
        if _START.search(raw):
            self.clear()
            self.active = True
            self.last_ai = random.choice(_OPENERS)
            self.used.add(self.last_ai)
            self.required = self.last_ai[-1]
            return f"好，成语接龙。我先出“{self.last_ai}”，现在轮到大家，接“{self.required}”字开头。"
        if _STOP.search(raw):
            self.clear()
            return "好，这局成语接龙先到这里。想玩别的，直接点一个。"
        if _TURN.search(raw):
            if self.last_user and self.last_ai:
                return (f"刚刚{self.last_nickname or '观众'}出的是“{self.last_user}”，我接的是“{self.last_ai}”。"
                        f"现在轮到大家，接“{self.required}”字开头。")
            return f"现在该大家接“{self.required}”字开头，我等的可是你们的成语。"
        if not _IDIOM.fullmatch(raw):
            return ""
        if raw in self.used:
            return f"{who}，“{raw}”这局已经用过了，不算。还是接“{self.required}”字开头，换一个。"
        if self.required and raw[0] != self.required:
            return (f"{who}，你出的“{raw}”是“{raw[0]}”开头，这轮要接“{self.required}”。"
                    f"这句先不算，还是你来。")
        self.last_user = raw
        self.last_nickname = who
        self.used.add(raw)
        tail = raw[-1]
        candidates = [word for word in _ANSWERS.get(tail, []) if word not in self.used]
        if not candidates:
            self.active = False
            return f"{who}的“{raw}”接住了，但我真想不出“{tail}”开头的了。这局算你赢，要不要换个开头再来？"
        answer = random.choice(candidates)
        self.last_ai = answer
        self.used.add(answer)
        self.required = answer[-1]
        praise = random.choice(("接得稳", "这个漂亮", "反应很快"))
        return f"{who}接“{raw}”，{praise}！我接“{answer}”。现在轮到大家，接“{self.required}”。"
