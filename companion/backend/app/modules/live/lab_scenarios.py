"""可回放的虚构观众数据。只负责生产 LiveEvent，不包含回应逻辑。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cue:
    at: float
    nickname: str
    content: str
    kind: str = "comment"
    gift: str = ""
    count: int = 0
    duplicate: bool = False


SCENARIOS = {
    "mixed": {
        "name": "完整试播", "description": "进场 → 聊游戏 → 提问 → 刷屏 → 礼物 → 追问 → 冷场", "duration": 58,
        "cues": [
            Cue(0, "小雨", "晚上好，第一次来！"), Cue(1, "阿哲", "今天准备聊什么？"),
            Cue(6, "泡芙", "下班回来有点累，想听你聊两句"),
            Cue(10, "阿哲", "你更喜欢种田游戏还是恐怖游戏？"),
            Cue(14, "小雨", "恐怖游戏不敢一个人玩怎么办？"),
            *[Cue(19 + i * .03, f"围观观众{i + 1}", "哈哈哈") for i in range(36)],
            Cue(20, "认真提问", "如果做双人游戏直播，你会怎么邀请观众一起玩？"),
            Cue(25, "星河", "送出 小心心×3", "gift", "小心心", 3),
            Cue(25.2, "星河", "送出 小心心×3", "gift", "小心心", 3, True),
            Cue(26, "晚风", "送出 星星×1", "gift", "星星", 1),
            Cue(31, "阿哲", "那就先从种田开始吧，你会先种什么？"),
            Cue(36, "小雨", "刚才说一起玩，那我负责钓鱼可以吗？"),
            Cue(40, "泡芙", "今天心情好多了，明天还来"),
        ],
    },
    "quiet": {
        "name": "低流量与冷场", "description": "少量观众、情绪回应、空白时间与主动开口", "duration": 42,
        "cues": [Cue(0, "路过的小猫", "嗨，有人在吗？"), Cue(9, "路过的小猫", "今天工作搞砸了一点，想安静待一会儿")],
    },
    "flood": {
        "name": "弹幕与礼物洪峰", "description": "600 条刷屏、重复重投、普通观众和礼物争抢注意力", "duration": 30,
        "cues": [
            *[Cue(1 + i * .001, f"观众{i}", "好耶！") for i in range(600)],
            Cue(2, "问号同学", "为什么刷屏的时候不能每条都回答？"),
            *[Cue(7 + i * .01, f"送礼观众{i}", "送出 星星×1", "gift", "星星", 1) for i in range(18)],
            Cue(9, "普通观众", "不送礼也可以一起聊吗？"),
            Cue(16, "普通观众", "那我们来聊最喜欢的游戏吧"),
        ],
    },
    "followup": {
        "name": "连续对话", "description": "相同观众追问、指代、改主意和话题接续", "duration": 42,
        "cues": [
            Cue(0, "阿哲", "你更喜欢种田游戏还是恐怖游戏？"),
            Cue(10, "阿哲", "那就种田吧，第一天先干什么？"),
            Cue(20, "小雨", "我来钓鱼，阿哲种地，主播做什么？"),
            Cue(30, "阿哲", "刚才说的分工我同意，农场叫什么名字？"),
        ],
    },
}


def scenario_public() -> list[dict]:
    return [{"id": key, "name": value["name"], "description": value["description"],
             "duration": value["duration"], "events": len(value["cues"])} for key, value in SCENARIOS.items()]
