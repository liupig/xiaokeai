"""键值设置存取（JSON 值）。"""
import json
import os
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from ..models import Setting
from ..paths import DATA_DIR, ROOT_DIR

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
    "modules": {"memory": True, "scenes": True, "rewrite": True, "keepsake": True, "tarot": True},
    "hardware": {
        "auto": False, "tier": "", "ram_gb": 0, "vram_gb": 0, "cores": 0,
        "reason": "", "fingerprint": "",
        "failed": {"stt": "", "tts": "", "memory": ""},
    },
}


_ENV_LOADED = False
_VOLC_CHAT_BASE = "https://ark.cn-beijing.volces.com/api/v3"
_KEY_ENVS = (
    "COMPANION_LLM_API_KEY",
    "ARK_API_KEY",
    "VOLC_ARK_API_KEY",
    "OPENAI_API_KEY",
    "DASHSCOPE_API_KEY",
    "LLM_API_KEY",
)


def _load_local_env() -> None:
    """读取本机 .env（已被 gitignore）。系统环境变量优先，不覆盖。"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    for path in (ROOT_DIR / ".env", ROOT_DIR / "scripts" / ".env", DATA_DIR / ".env"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


def env_llm() -> Dict[str, Any]:
    """系统 / .env 里的 LLM 配置。不落库。"""
    _load_local_env()
    key = ""
    key_src = ""
    for name in _KEY_ENVS:
        val = (os.environ.get(name) or "").strip()
        if val:
            key, key_src = val, name
            break
    base = (os.environ.get("COMPANION_LLM_BASE_URL") or "").strip()
    model = (os.environ.get("COMPANION_LLM_MODEL") or "").strip()
    if not base and key_src in ("ARK_API_KEY", "VOLC_ARK_API_KEY"):
        base = _VOLC_CHAT_BASE
    out: Dict[str, Any] = {}
    if key:
        out["api_key"] = key
    if base:
        out["base_url"] = base.rstrip("/")
    if model:
        out["model"] = model
    return out


def llm_overlay() -> Dict[str, Any]:
    return env_llm()


def apply_llm_overlay(llm: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """前端没填 API Key 时，回退到环境变量。前端有 Key 则完全以前端为准。"""
    out = dict(llm or {})
    env = env_llm()
    if (out.get("api_key") or "").strip() or not env.get("api_key"):
        return out
    out["api_key"] = env["api_key"]
    if env.get("base_url"):
        out["base_url"] = env["base_url"]
    if env.get("model"):
        out["model"] = env["model"]
        if "character" in str(env["model"]).lower():
            out["thinking"] = "default"
    return out


def llm_env_fallback(llm: Optional[Dict[str, Any]] = None) -> bool:
    stored = dict(llm or {})
    return bool(env_llm().get("api_key")) and not (stored.get("api_key") or "").strip()


def saved_keys(session: Session) -> set:
    """数据库里真正写过的设置键（不含仅内存默认值）。"""
    keys = set()
    for row in session.exec(select(Setting)).all():
        if row.key != "cam_review":
            keys.add(row.key)
    return keys


def _read_all(session: Session) -> Dict[str, Any]:
    result = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULTS.items()}
    for row in session.exec(select(Setting)).all():
        if row.key == "cam_review":
            continue
        try:
            value = json.loads(row.value)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(result.get(row.key), dict):
            result[row.key].update(value)
        else:
            result[row.key] = value
    return result


def get_all(session: Session) -> Dict[str, Any]:
    """运行时配置：前端没填 Key 时补上环境变量。"""
    result = _read_all(session)
    result["llm"] = apply_llm_overlay(result.get("llm") or {})
    return result


def public_all(session: Session) -> Dict[str, Any]:
    """给前端的配置：不回传环境变量里的 Key。"""
    result = _read_all(session)
    llm = dict(result.get("llm") or {})
    using_env = llm_env_fallback(llm)
    result["llm_env"] = using_env
    result["llm_local"] = using_env
    return result


def update(session: Session, patch: Dict[str, Any]) -> Dict[str, Any]:
    patch = dict(patch)
    patch.pop("llm_local", None)
    patch.pop("llm_env", None)
    for key, value in patch.items():
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=json.dumps(value, ensure_ascii=False))
            session.add(row)
        else:
            row.value = json.dumps(value, ensure_ascii=False)
    session.commit()
    return get_all(session)
