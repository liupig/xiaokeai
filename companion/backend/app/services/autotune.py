"""按本机配置选 ASR / TTS / 记忆；本地依赖起不来就回退到免费在线，保证进程能起来。"""
from __future__ import annotations

import importlib.util
from typing import Any, Dict, List

from sqlmodel import Session

from . import settings_store
from .machine import probe as probe_machine

EDGE_VOICE = "zh-CN-XiaoyiNeural"
QWEN_VOICE = "Serena"


def _has_mod(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _asr_files_ok() -> bool:
    from . import asr as asr_svc
    return bool(asr_svc._model_ready())


def _qwen_ready(size: str) -> bool:
    from . import tts_qwen
    try:
        return bool(tts_qwen._local_ready(tts_qwen.normalize_size(size)))
    except Exception:
        return False


def _embed_ok() -> bool:
    try:
        from ..modules.memory.embed_local import _fastembed_cache_ok, _torch_weight_dir
        return bool(_fastembed_cache_ok() or _torch_weight_dir() is not None)
    except Exception:
        return False


def _hw_blob(conf: Dict[str, Any]) -> Dict[str, Any]:
    raw = dict(conf.get("hardware") or {})
    failed = dict(raw.get("failed") or {})
    return {
        "auto": bool(raw.get("auto", False)),
        "tier": str(raw.get("tier") or ""),
        "ram_gb": float(raw.get("ram_gb") or 0),
        "vram_gb": float(raw.get("vram_gb") or 0),
        "cores": int(raw.get("cores") or 0),
        "reason": str(raw.get("reason") or ""),
        "fingerprint": str(raw.get("fingerprint") or ""),
        "failed": {
            "stt": str(failed.get("stt") or ""),
            "tts": str(failed.get("tts") or ""),
            "memory": str(failed.get("memory") or ""),
        },
    }


def recommend(spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    spec = spec or probe_machine()
    ram = float(spec.get("ram_gb") or 0)
    vram = float(spec.get("vram_gb") or 0)
    cores = int(spec.get("cores") or 2)
    reasons: List[str] = []

    sherpa = _has_mod("sherpa_onnx")
    qwen_pkg = _has_mod("qwen_tts")
    mem0 = _has_mod("mem0")
    asr_files = _asr_files_ok()
    qwen_06 = _qwen_ready("0.6b")
    qwen_17 = _qwen_ready("1.7b")
    embed = _embed_ok()

    want_qwen = vram >= 5.5 and ram >= 8 and qwen_pkg and qwen_06
    qwen_size = "1.7b" if want_qwen and vram >= 10 and qwen_17 else "0.6b"
    if want_qwen and qwen_size == "1.7b" and not qwen_17:
        qwen_size = "0.6b"

    want_asr = ram >= 8 and cores >= 4 and sherpa and asr_files
    want_memory = ram >= 12 and mem0 and embed

    if ram < 8:
        reasons.append(f"内存 {ram}GB 偏低")
        want_qwen = False
        want_asr = False
        want_memory = False
    if vram < 5.5:
        reasons.append("无可用独显或显存不足，本地 TTS 不启动")
        want_qwen = False
    if not qwen_pkg:
        reasons.append("未安装 qwen-tts")
        want_qwen = False
    if want_qwen and not qwen_06:
        reasons.append("本地没有 Qwen TTS 权重")
        want_qwen = False
    if not sherpa:
        reasons.append("未安装 sherpa-onnx")
        want_asr = False
    if ram >= 8 and not asr_files:
        reasons.append("本地没有 SenseVoice 模型")
        want_asr = False
    if ram < 12:
        reasons.append("内存不足以开记忆")
        want_memory = False
    elif not mem0:
        reasons.append("未安装 mem0，记忆关闭")
        want_memory = False
    elif not embed:
        reasons.append("本地没有向量模型，记忆关闭")
        want_memory = False

    if want_qwen:
        tier = "high"
    elif ram >= 8:
        tier = "mid"
    else:
        tier = "low"

    if want_qwen:
        reasons.append(f"TTS 用本地 Qwen {qwen_size}")
    else:
        reasons.append("TTS 用免费在线 edge-tts")
    if want_asr:
        reasons.append("ASR 用本地 SenseVoice")
    else:
        reasons.append("ASR 用浏览器免费识别")
    if want_memory:
        reasons.append("记忆开启")
    else:
        reasons.append("记忆关闭")

    physics = False
    pixel = 2 if ram >= 8 else 1
    return {
        "tier": tier,
        "stt_engine": "sensevoice" if want_asr else "browser",
        "tts_engine": "qwen" if want_qwen else "edge",
        "qwen_size": qwen_size,
        "tts_voice": QWEN_VOICE if want_qwen else EDGE_VOICE,
        "memory": want_memory,
        "physics": physics,
        "pixel_ratio_cap": pixel,
        "reason": "；".join(reasons),
        **spec,
    }


def _should_apply(session: Session, conf: Dict[str, Any]) -> bool:
    keys = settings_store.saved_keys(session)
    fresh = not (keys & {"tts", "stt", "modules", "hardware"})
    hw_saved = "hardware" in keys
    auto = hw_saved and bool((conf.get("hardware") or {}).get("auto"))
    return fresh or auto


def _apply_failed(rec: Dict[str, Any], failed: Dict[str, str]) -> Dict[str, Any]:
    out = dict(rec)
    extra: List[str] = []
    if failed.get("stt"):
        out["stt_engine"] = "browser"
        extra.append("ASR 上次本地启动失败，继续用浏览器")
    if failed.get("tts"):
        out["tts_engine"] = "edge"
        out["tts_voice"] = EDGE_VOICE
        extra.append("TTS 上次本地启动失败，继续用在线")
    if failed.get("memory"):
        out["memory"] = False
        extra.append("记忆上次启动失败，保持关闭")
    if extra:
        out["reason"] = (out.get("reason") or "") + "；" + "；".join(extra)
    return out


def apply_on_boot(session: Session) -> Dict[str, Any]:
    conf = settings_store.get_all(session)
    spec = probe_machine()
    rec = recommend(spec)
    hw = _hw_blob(conf)
    if hw.get("fingerprint") and hw["fingerprint"] != spec.get("fingerprint"):
        hw["failed"] = {"stt": "", "tts": "", "memory": ""}
        print(f"[autotune] machine fingerprint changed {hw.get('fingerprint')} -> {spec.get('fingerprint')}")
    rec = _apply_failed(rec, hw["failed"])

    if not _should_apply(session, conf):
        hw.update({
            "tier": rec["tier"],
            "ram_gb": rec["ram_gb"],
            "vram_gb": rec["vram_gb"],
            "cores": rec["cores"],
            "fingerprint": rec["fingerprint"],
        })
        if hw.get("reason") != rec["reason"] or hw.get("tier") != rec["tier"]:
            hw["reason"] = rec["reason"]
            settings_store.update(session, {"hardware": hw})
        print(
            f"[autotune] skip engines (user lock) tier={rec['tier']} "
            f"ram={rec['ram_gb']}GB vram={rec['vram_gb']}GB"
        )
        return settings_store.get_all(session)

    tts = dict(conf.get("tts") or {})
    tts["engine"] = rec["tts_engine"]
    tts["qwen_size"] = rec["qwen_size"]
    tts["voice"] = rec["tts_voice"]
    stt = dict(conf.get("stt") or {})
    stt["engine"] = rec["stt_engine"]
    modules = dict(conf.get("modules") or {})
    modules["memory"] = bool(rec["memory"])
    quality = dict(conf.get("quality") or {})
    if rec["tier"] == "low":
        quality["physics"] = False
        quality["pixel_ratio_cap"] = 1
    hw.update({
        "auto": True,
        "tier": rec["tier"],
        "ram_gb": rec["ram_gb"],
        "vram_gb": rec["vram_gb"],
        "cores": rec["cores"],
        "reason": rec["reason"],
        "fingerprint": rec["fingerprint"],
        "failed": hw["failed"],
    })
    out = settings_store.update(session, {
        "tts": tts,
        "stt": stt,
        "modules": modules,
        "quality": quality,
        "hardware": hw,
    })
    print(
        f"[autotune] applied tier={rec['tier']} ram={rec['ram_gb']}GB "
        f"vram={rec['vram_gb']}GB asr={rec['stt_engine']} tts={rec['tts_engine']} "
        f"memory={rec['memory']} | {rec['reason']}"
    )
    return out


def lock_user_override(session: Session, patch: Dict[str, Any]) -> Dict[str, Any]:
    """用户从设置页保存引擎 / 模块时，关掉自动档。"""
    if not any(k in patch for k in ("tts", "stt", "modules", "quality")):
        return patch
    conf = settings_store.get_all(session)
    hw = _hw_blob(conf)
    incoming = patch.get("hardware")
    if isinstance(incoming, dict):
        hw.update({k: incoming[k] for k in incoming if k != "failed"})
        if isinstance(incoming.get("failed"), dict):
            hw["failed"].update({k: str(v or "") for k, v in incoming["failed"].items()})
    hw["auto"] = False
    if "stt" in patch:
        hw["failed"]["stt"] = ""
    if "tts" in patch:
        hw["failed"]["tts"] = ""
    if "modules" in patch:
        prev = bool((conf.get("modules") or {}).get("memory", True))
        now = bool((patch.get("modules") or {}).get("memory", prev))
        if now:
            hw["failed"]["memory"] = ""
    patch = dict(patch)
    patch["hardware"] = hw
    return patch


def fallback_stt(reason: str) -> None:
    from ..db import engine
    from . import asr as asr_svc

    with Session(engine) as session:
        conf = settings_store.get_all(session)
        stt = dict(conf.get("stt") or {})
        if (stt.get("engine") or "").strip().lower() == "browser":
            return
        stt["engine"] = "browser"
        hw = _hw_blob(conf)
        hw["failed"]["stt"] = reason[:400]
        hw["reason"] = f"ASR 已改用浏览器免费识别：{reason}"[:400]
        settings_store.update(session, {"stt": stt, "hardware": hw})
    try:
        asr_svc.release()
    except Exception:
        pass
    print(f"[autotune] ASR -> browser ({reason})")


def fallback_tts(reason: str) -> None:
    from ..db import engine
    from . import tts_qwen

    with Session(engine) as session:
        conf = settings_store.get_all(session)
        tts = dict(conf.get("tts") or {})
        if (tts.get("engine") or "").strip().lower() in ("edge", "browser", "off"):
            return
        tts["engine"] = "edge"
        tts["voice"] = EDGE_VOICE
        hw = _hw_blob(conf)
        hw["failed"]["tts"] = reason[:400]
        hw["reason"] = f"TTS 已改用免费在线 edge-tts：{reason}"[:400]
        settings_store.update(session, {"tts": tts, "hardware": hw})
    try:
        tts_qwen.release()
    except Exception:
        pass
    print(f"[autotune] TTS -> edge ({reason})")


def fallback_memory(reason: str) -> None:
    from ..db import engine
    from ..modules.memory import worker as memory_worker

    with Session(engine) as session:
        conf = settings_store.get_all(session)
        modules = dict(conf.get("modules") or {})
        if not modules.get("memory", True):
            return
        modules["memory"] = False
        hw = _hw_blob(conf)
        hw["failed"]["memory"] = reason[:400]
        hw["reason"] = f"记忆已关闭：{reason}"[:400]
        settings_store.update(session, {"modules": modules, "hardware": hw})
    try:
        memory_worker.release()
    except Exception:
        pass
    print(f"[autotune] memory off ({reason})")
