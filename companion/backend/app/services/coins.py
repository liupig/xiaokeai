"""金币外壳。规则在编译好的 coins_box 里，这里只把三个入口交出去。"""
import re

from . import coins_box as _box

CoinError = _box.CoinError
BURN = _box.BURN
heartbeat = _box.heartbeat
balance = _box.balance
pay = _box.pay
redeem = _box.redeem
preview = _box.preview

_PURSE = {
    "zh-CN": "对方钱包里现在有 {n} 枚金币。问到有多少钱、多少金币、余额，只说这个数，不要把许愿落下的枚数加总。没问就不要提。",
    "en": "The wallet holds {n} coins right now. If asked how much money or how many coins, say this number only. Do not add up wish drops. Do not mention it unless asked.",
    "ja": "相手の財布には今コインが {n} 枚ある。いくら持っているか聞かれたらこの数だけ言う。願いで落ちた枚数を足さない。聞かれなければ言わない。",
    "ko": "지갑에는 지금 코인이 {n}개 있다. 돈이 얼마인지 물으면 이 숫자만 말한다. 소원으로 떨어진 개수를 더하지 않는다. 묻기 전에는 말하지 않는다.",
}


def format_coins(milli: int) -> str:
    """和界面药丸同一套：一百枚以上取整，不到一百保留一位小数。"""
    value = abs(int(milli))
    whole, frac = divmod(value, 1000)
    if whole >= 100:
        text = str(whole)
    else:
        tenths = frac // 100
        text = str(whole) if tenths == 0 else f"{whole}.{tenths}"
    return f"-{text}" if int(milli) < 0 else text


_NOT_PURSE = re.compile(r"股价|金价|房价|物价|多少钱一|卖多少")
_SAY = {
    "zh-CN": "你现在有 {n} 枚金币。",
    "en": "You have {n} coins.",
    "ja": "今、コインは {n} 枚ある。",
    "ko": "지금 코인은 {n}개야.",
}


def asks_purse(text: str) -> bool:
    """问的是自己钱包里的总数。股价、这次落下多少，都不算。"""
    raw = re.sub(r"[\s?？!！。，,~～]", "", text or "")
    if not raw or len(raw) > 40:
        return False
    if _NOT_PURSE.search(raw):
        return False
    if "落下" in raw and not re.search(r"一共|所有|余额|钱包|总共", raw):
        return False
    if re.search(r"你(?:现在|目前|到底|究竟)?有多少(?:钱|金币)", raw):
        return True
    mine = bool(re.search(r"我|咱|余额|钱包", raw) or (
        "金币" in raw and re.search(r"所有|一共|总共|余额|还有|现在", raw)
    ))
    return mine and bool(re.search(r"多少|几枚|几个|总共|一共|所有|全部", raw))


def purse_say(milli: int | None = None) -> str:
    """念给对方的余额。只有盒子里的数。"""
    if milli is None:
        try:
            milli = int(_box.balance())
        except Exception:
            return ""
    from ..locale_pack import current_reply

    lang = current_reply()
    template = _SAY.get(lang) or _SAY["zh-CN"]
    return template.format(n=format_coins(int(milli)))


def purse_line(milli: int | None = None) -> str:
    """给模型的余额。数字来自盒子，不来自许愿记忆。"""
    if milli is None:
        try:
            milli = int(_box.balance())
        except Exception:
            return ""
    from ..locale_pack import current_reply

    lang = current_reply()
    template = _PURSE.get(lang) or _PURSE["zh-CN"]
    return template.format(n=format_coins(int(milli)))
