"""键值设置存取（JSON 值）。"""
import json
from typing import Any, Dict

from sqlmodel import Session, select

from ..models import Setting

DEFAULTS: Dict[str, Any] = {
    # thinking: default=跟随模型默认 / on=强制开启思考 / off=强制关闭思考
    # max_tokens 为 0 表示不传该参数（用服务商默认值）
    "llm": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": "",
            "model": "qwen-plus", "temperature": 0.85, "top_p": 1.0,
            "max_tokens": 0, "thinking": "default"},
    "tts": {"engine": "qwen", "voice": "Vivian", "rate": "+0%", "qwen_size": "0.6b",
            "qwen_style": "yujie", "qwen_instruct": "",
            "duplex_cmd": "interrupt_or_queue", "duplex_remain_sec": 3,
            "duplex_delayed_sec": 16, "duplex_proactive_sec": 45,
            "duplex_goodbye_sec": 140, "duplex_session_max_min": 0,
            "duplex_filler": False, "duplex_ingress": True},
    "stt": {"engine": "sensevoice"},  # browser=在线 Web Speech；sensevoice=离线 SenseVoice
    "download": {"aplaybox_token": ""},
    "quality": {"physics": True, "pixel_ratio_cap": 2, "camera_follow": False, "bgm_volume": 0.5,
                "background_color": "#141420", "background_image": "", "light_level": 1.0,
                # 圆形舞台底座：显隐 / 台面颜色 / 发光环颜色 / 风格 / 台面贴图 / 不透明度
                "stage_show": True, "stage_color": "#232342", "stage_glow": "#5b5bd6",
                "stage_style": "classic", "stage_texture": "", "stage_opacity": 1.0},
    "modules": {"memory": True, "scenes": True, "rewrite": True, "keepsake": True},
}


def get_all(session: Session) -> Dict[str, Any]:
    result = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULTS.items()}
    for row in session.exec(select(Setting)).all():
        if row.key == "cam_review":
            continue
        try:
            value = json.loads(row.value)
        except json.JSONDecodeError:
            continue
        # 字典按键合并，保证新增的默认键不被旧数据覆盖丢失
        if isinstance(value, dict) and isinstance(result.get(row.key), dict):
            result[row.key].update(value)
        else:
            result[row.key] = value
    return result


def update(session: Session, patch: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in patch.items():
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=json.dumps(value, ensure_ascii=False))
            session.add(row)
        else:
            row.value = json.dumps(value, ensure_ascii=False)
    session.commit()
    return get_all(session)
