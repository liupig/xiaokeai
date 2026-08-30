"""重说提示注入。"""
from typing import Dict, List


def inject_variation(messages: List[Dict[str, str]], variation: str) -> List[Dict[str, str]]:
    hint = (variation or "").strip() or "换个说法，不要重复上一句的措辞和句式。"
    out = list(messages)
    out.append({
        "role": "system",
        "content": (
            "这是「重说」：同一轮用户话再答一遍。"
            f"{hint} 表演标记仍要给，不要解释你在重说。"
        ),
    })
    return out
