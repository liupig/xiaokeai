"""Companion Studio 后端入口。"""
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .db import engine, init_db
from .models import CamReview, Character, SceneState  # noqa: F401 — register table
from .paths import ASSETS_DIR, KEEPSAKES_DIR
from .routers import assets, characters, chat, download, review, settings, speech
from .modules.memory.router import router as memory_router
from .modules.scenes.router import router as scenes_router
from .modules.rewrite.router import router as rewrite_router
from .modules.keepsake.router import router as keepsake_router
from .services import catalog
from .services import asr as asr_svc
from .services import review_store
from .services import settings_store
from .services import tts_qwen

app = FastAPI(title="Companion Studio API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Audio-Format", "X-Audio-Rate"],
)

app.include_router(assets.router)
app.include_router(characters.router)
app.include_router(chat.router)
app.include_router(speech.router)
app.include_router(settings.router)
app.include_router(download.router)
app.include_router(review.router)
app.include_router(memory_router)
app.include_router(scenes_router)
app.include_router(rewrite_router)
app.include_router(keepsake_router)

app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/keepsakes", StaticFiles(directory=str(KEEPSAKES_DIR)), name="keepsakes")

DEFAULT_PERSONA = (
    "你叫清宵，是一位国风御姐系虚拟陪玩。性格：温柔中带一点撩人，说话自信从容，"
    "偶尔调侃用户但分寸得体。喜欢古风音乐和舞蹈，擅长跳极乐净土。"
    "称呼用户为「小哥哥」或按用户要求。"
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    with Session(engine) as session:
        n = review_store.migrate_if_needed(session)
        if n:
            print(f"[review] migrated {n} cam_review rows")
        catalog.scan_all(session)
        dropped = catalog.unbind_nondance_bgm(session)
        if dropped:
            print(f"[catalog] unbound bgm from {dropped} non-dance motions")
        purged = catalog.purge_unreferenced_audio(session)
        if purged:
            print(f"[catalog] deleted {purged} non-dance audio files")
        # 默认角色：清宵
        if not session.exec(select(Character)).first():
            from .models import Asset
            model = session.exec(
                select(Asset).where(Asset.kind == "model", Asset.name == "qingxiao")
            ).first()
            session.add(Character(
                name="清宵",
                model_asset_id=model.id if model else 0,
                persona=DEFAULT_PERSONA,
                greeting="小哥哥，你来啦～想聊点什么，还是想看我跳支舞？",
                voice="",
            ))
            session.commit()
        _migrate_tts_to_local_qwen(session)
    threading.Thread(target=_warmup_offline_speech, daemon=True).start()


def _migrate_tts_to_local_qwen(session: Session) -> None:
    """默认改回本地 Qwen 流式。云端 edge/cosy 仅作备选，不自动留下。"""
    tts_conf = settings_store.get_all(session).get("tts") or {}
    if tts_conf.get("engine") == "qwen":
        return
    tts_conf["engine"] = "qwen"
    allowed = {v["id"] for v in tts_qwen.QWEN_VOICES}
    if tts_conf.get("voice") not in allowed:
        tts_conf["voice"] = "Vivian"
    settings_store.update(session, {"tts": tts_conf})


def _warmup_offline_speech() -> None:
    """启动后并行拉起 ASR CPU 进程、TTS GPU 进程、记忆抽取进程。"""
    asr_thread = threading.Thread(target=_warmup_asr, daemon=True)
    tts_thread = threading.Thread(target=_warmup_tts, daemon=True)
    mem_thread = threading.Thread(target=_warmup_memory, daemon=True)
    asr_thread.start()
    tts_thread.start()
    mem_thread.start()


def _warmup_memory() -> None:
    from .modules.memory import worker as memory_worker
    try:
        memory_worker.ensure()
    except Exception as exc:
        print(f"[memory] worker start failed: {exc}")


def _warmup_asr() -> None:
    try:
        asr_svc.warmup()
    except Exception as exc:
        asr_svc._state["message"] = str(exc)
        asr_svc._state["downloading"] = False


def _warmup_tts() -> None:
    with Session(engine) as session:
        tts_conf = settings_store.get_all(session).get("tts") or {}
    if tts_conf.get("engine") != "qwen":
        return
    try:
        tts_qwen.warmup(tts_conf.get("qwen_size") or "0.6b")
    except Exception as exc:
        tts_qwen._state["message"] = str(exc)
        tts_qwen._state["loading"] = False
        tts_qwen._state["downloading"] = False


@app.get("/api/health")
def health():
    return {"ok": True}
