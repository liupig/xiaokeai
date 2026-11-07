"""明确、无歧义的模型外观命令。只处理确定性操作，不代替 LLM 表演。"""
import re
from typing import Dict, Optional


_REMOVE_GLASSES = re.compile(
    r"(摘掉|取下|脱下|去掉|摘除|别[戴带]|不[戴带]|不要[戴带]| remove | take off ).*眼镜"
    r"|眼镜.*(摘掉|取下|脱下|去掉|摘除)"
    r"|(remove|take off).*glasses",
    re.IGNORECASE,
)
_WEAR_GLASSES = re.compile(
    r"(戴上|带上|佩戴|wear|put on).*眼镜|(wear|put on).*glasses",
    re.IGNORECASE,
)
_GLASSES_NAMES = {
    "圆": "round_glasses",
    "round": "round_glasses",
    "方": "square_glasses",
    "square": "square_glasses",
    "墨镜": "sunglasses",
    "sunglasses": "sunglasses",
    "椭圆": "oval_glasses",
    "oval": "oval_glasses",
}


def direct_outfit_event(text: str) -> Optional[Dict[str, str]]:
    if _REMOVE_GLASSES.search(text or ""):
        return {"type": "outfit", "value": "glasses:off"}
    if _WEAR_GLASSES.search(text or ""):
        lowered = text.lower()
        name = next((value for key, value in _GLASSES_NAMES.items() if key in lowered), "glasses")
        return {"type": "outfit", "value": f"{name}:on"}
    return None
