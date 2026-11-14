"""Session-local, explicit user preferences; no inferred psychological labels."""
from __future__ import annotations

import re
import threading
import time


class CompanionIntent:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.goal = ''
            self.mode = '陪伴'
            self.last_user = ''
            self.updated = 0.0

    def user(self, text: str):
        with self.lock:
            self.last_user = text.strip()[:200]
            self.updated = time.time()
            if re.search(r'不练了|不打了|换个目标|取消目标', text):
                self.goal = ''
            elif re.search(r'想练|练习|这把.*(?:想|目标)|今天.*(?:想|目标)|我想.*(?:玩|试|建|通关)', text):
                self.goal = text.strip()[:160]
            if re.search(r'别分析|不想听建议|就想吐槽|听我吐槽', text):
                self.mode = '倾听'
            elif re.search(r'别说话|安静|别打扰', text):
                self.mode = '安静'
            elif re.search(r'帮我分析|复盘|怎么打|怎么出装|给.*建议', text):
                self.mode = '讨论'
            elif re.search(r'聊聊天|陪我聊|可以说话|多说点|多多说话|怎么(?:都)?不说话|你都不说话', text):
                self.mode = '陪聊'

    def context(self) -> str:
        with self.lock:
            goal, mode, last, age = self.goal, self.mode, self.last_user, time.time() - self.updated
        rules = {
            '倾听': '先接住用户原话中的具体感受，不讲道理、不自动给攻略、不附带追问清单。',
            '安静': '用户明确要求安静，不主动发言；只在用户再次发问或允许聊天后回应。',
            '讨论': '用户愿意分析，先回答正在问的一个问题，给依据和一个可选建议；别把之后每次事件都变成教学。',
            '陪聊': '可以聊游戏偏好与共同经历，问题一次一个；没得到回应就留白，不追问。',
            '陪伴': '根据具体事件自然回应，用户没有主动求建议时不连续教学。',
        }
        # Analysis is a short-lived request; explicit quiet/listening preferences persist.
        if mode == '讨论' and age > 90:
            mode = '陪伴'
        lines = ['【用户明确表达的相处偏好】' + rules[mode]]
        if goal:
            lines.append('本次用户目标原话：' + goal + '。只在相关进展出现时自然接起，不每轮复述。')
        if last and age <= 90:
            lines.append('最近用户原话：' + last + '。以原话表达为准，不从战绩擅自推断情绪。')
        return '\n'.join(lines)


companion_intent = CompanionIntent()
