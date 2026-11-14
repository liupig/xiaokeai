"""Short-lived user corrections override stale narration, never become permanent memory."""
import re
import threading
import time

_lock = threading.Lock()
_corrections = {}


def note(character_id, text):
    match = re.search(r'我(?:这把|这局)?(?:玩的是|玩的|用的是|用的|选的是|选的)\s*([^，。！？!?\s]{1,16})', text or '')
    if match:
        with _lock:
            _corrections[character_id] = (match.group(1), time.time())


def context(character_id):
    from ..sight.league_client import snapshot, roster_brief
    state = snapshot()
    from ..sight.league_companion import strategy
    now = time.time()
    with _lock:
        correction = _corrections.get(character_id)
    if correction and now - correction[1] < 1800:
        fact = '用户最近明确纠正：本局玩的英雄是' + correction[0] + '。撤销历史里不一致的英雄判断；若API冲突先说明冲突，不强行反驳用户。'
    elif state and now - state.get('observed_at', 0) <= 5:
        fact = '本机API当前确认的玩家英雄：' + state['hero'] + '。'
    else:
        fact = '当前玩家英雄未得到新鲜证据确认。历史台词中的英雄和战绩不能代替当前事实。'
    from . import along
    from .eyes_host import eyes_status
    watching = along.snapshot()
    phase = eyes_status().get('eyes')
    runtime = (f"当前陪玩{'开启' if watching.get('on') else '关闭'}；视觉状态：{phase}。"
               "仅up或remote表示视觉服务可用，也不代表这轮已取得截图。"
               "用户问为什么不说话时依据实际状态回答，不编怕打扰、看入迷或用户嫌吵的理由。"
               "没有本轮截图证据，不声称看见桌面、游戏在动、窗口被挡或需要切全屏。")
    return ('【当前游戏事实约束】' + fact + '\n' + runtime +
            ('\n' + roster_brief(state) if state and now - state.get('observed_at', 0) <= 5 else '') +
            ('\n' + strategy(state, []) if state and now - state.get('observed_at', 0) <= 5 else '') +
            '历史助手发言不是游戏证据，不能用自己说过的蹲草、闪现、胜负来证明它发生过。'
            '不根据旧结算宣称本局结束；没有新证据不评论操作。不评价用户菜、补刀少或强迫换简单英雄。')
