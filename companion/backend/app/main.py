"""xiaoke.ai 后端入口。"""
import threading
import warnings

# Triton 在缺 CUDA Toolkit 时会刷 Failed to find CUDA/cuobjdump；推理仍走已编译的 torch 核。
warnings.filterwarnings("ignore", message=r"Failed to find .*", module=r"triton(\.|$)")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .db import engine, init_db
from .models import CamReview, Character, CoinNote, CoinWallet, SceneState  # noqa: F401 — register table
from .paths import KEEPSAKES_DIR, resolve_asset_file
from .routers import assets, characters, chat, coins, download, omni, review, settings, speech
from .modules.memory.router import router as memory_router
from .modules.scenes.router import router as scenes_router
from .modules.rewrite.router import router as rewrite_router
from .modules.keepsake.router import router as keepsake_router
from .modules.tarot.router import router as tarot_router
from .modules.codewatch.router import router as codewatch_router
from .modules.harness.router import router as harness_router
from .modules.glance.router import router as glance_router
from .services import catalog
from .services import asr as asr_svc
from .services import review_store
from .services import settings_store
from .services import tts_qwen
from . import proc_reap


app = FastAPI(title="xiaoke.ai", version="0.1.0")

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
app.include_router(omni.router)
app.include_router(settings.router)
app.include_router(coins.router)
app.include_router(download.router)
app.include_router(review.router)
app.include_router(memory_router)
app.include_router(scenes_router)
app.include_router(rewrite_router)
app.include_router(keepsake_router)
app.include_router(tarot_router)
app.include_router(codewatch_router)
app.include_router(harness_router)
app.include_router(glance_router)


@app.get("/lab/watch", include_in_schema=False)
def watch_lab():
    """陪看调试页。不挂进桌面、网页或桌宠。"""
    from pathlib import Path

    from fastapi.responses import FileResponse

    page = Path(__file__).resolve().parent / "modules" / "glance" / "lab.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="lab page missing")
    return FileResponse(page, media_type="text/html", headers={"Cache-Control": "no-store"})

@app.get("/assets/{path:path}", include_in_schema=False)
def serve_asset(path: str):
    fp = resolve_asset_file(path)
    if fp is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(fp)


app.mount("/keepsakes", StaticFiles(directory=str(KEEPSAKES_DIR)), name="keepsakes")


@app.on_event("startup")
def startup() -> None:
    n = proc_reap.reap_dead_workers()
    if n:
        print(f"[proc] reaped {n} leftover workers from last run")
    import atexit
    atexit.register(proc_reap.shutdown_workers)
    init_db()
    from .paths import ASSETS_DIR, content_status
    st = content_status()
    print(f"[paths] assets={ASSETS_DIR}")
    print(f"[content] packed={st['packed']} ok={st['ok']} path={st['path'] or '-'}")
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
        seeded = catalog.ensure_default_characters(session)
        if seeded:
            print(f"[character] seeded {seeded} default characters")
        from .services import autotune
        autotune.apply_on_boot(session)
        env = settings_store.env_llm()
        if env.get("api_key"):
            print(
                f"[llm] env fallback ready model={env.get('model') or '-'} "
                f"base={env.get('base_url') or '-'} (used when settings api_key is empty)"
            )
    try:
        from .modules.glance.eyes_host import bind_running
        bind_running()
    except Exception:
        pass
    _compact_wallet()
    threading.Thread(target=_warmup_offline_speech, daemon=True).start()
    threading.Thread(target=_open_watch_lab, daemon=True).start()
    atexit.register(_release_glance)


def _compact_wallet() -> None:
    """开机把过长的账本收成一块快照。记账在单独的进程里。"""
    try:
        from .services import ledger
        ledger.start()
        if ledger.call("compact"):
            print("[coins] folded the chain into one checkpoint")
    except Exception as exc:
        print(f"[coins] compact skipped: {exc}")


def _open_watch_lab() -> None:
    """记录页是固定地址。截图开关开着时，跟服务一起打开。"""
    import time
    import webbrowser

    time.sleep(1.2)
    from .modules.glance.archive import keeping, lab_url

    if not keeping():
        print("[glance] 截图不落盘，记录页不自动打开")
        return
    url = lab_url()
    print(f"[glance] 记录页 {url}")
    try:
        webbrowser.open(url)
    except OSError as exc:
        print(f"[glance] 记录页没有打开：{exc}")


def _speech_engines() -> tuple[str, str]:
    with Session(engine) as session:
        conf = settings_store.get_all(session)
    tts_eng = ((conf.get("tts") or {}).get("engine") or "").strip().lower()
    stt_eng = ((conf.get("stt") or {}).get("engine") or "").strip().lower()
    return tts_eng, stt_eng


def _memory_enabled() -> bool:
    with Session(engine) as session:
        return bool((settings_store.get_all(session).get("modules") or {}).get("memory", True))


def _warmup_offline_speech() -> None:
    """只预热当前选中的本地引擎。浏览器 ASR / edge-tts 不拉 SenseVoice、Qwen。"""
    tts_eng, stt_eng = _speech_engines()
    print(f"[speech] startup engines tts={tts_eng or 'unset'} stt={stt_eng or 'unset'}")
    threads: list[threading.Thread] = []
    if _memory_enabled():
        threads.append(threading.Thread(target=_warmup_memory, daemon=True))
    else:
        print("[memory] skip warmup (module off)")
    if stt_eng == "sensevoice":
        threads.append(threading.Thread(target=_warmup_asr, daemon=True))
    else:
        print("[asr] skip warmup (engine is not sensevoice)")
    if tts_eng == "qwen":
        threads.append(threading.Thread(target=_warmup_tts, daemon=True))
    else:
        print("[tts] skip warmup (engine is not qwen)")
    for t in threads:
        t.start()


def _warmup_memory() -> None:
    from .modules.memory import worker as memory_worker
    from .services import autotune
    try:
        memory_worker.ensure()
    except Exception as exc:
        print(f"[memory] worker start failed: {exc}")
        autotune.fallback_memory(str(exc))


def _warmup_asr() -> None:
    from .services import autotune
    try:
        asr_svc.warmup(download=False)
    except Exception as exc:
        asr_svc._state["message"] = str(exc)
        asr_svc._state["downloading"] = False
        print(f"[asr] warmup failed: {exc}")
        autotune.fallback_stt(str(exc))


def _warmup_tts() -> None:
    from .services import autotune
    with Session(engine) as session:
        tts_conf = settings_store.get_all(session).get("tts") or {}
    if tts_conf.get("engine") != "qwen":
        return
    try:
        tts_qwen.warmup(tts_conf.get("qwen_size") or "0.6b", download=False)
    except Exception as exc:
        tts_qwen._state["message"] = str(exc)
        tts_qwen._state["loading"] = False
        tts_qwen._state["downloading"] = False
        print(f"[tts] warmup failed: {exc}")
        autotune.fallback_tts(str(exc))


def _release_glance() -> None:
    """退出时停掉陪看，并关掉本机视觉进程。关掉按钮走同一条。"""
    try:
        from .modules.glance.along import stop as along_stop
        along_stop()
    except Exception:
        pass
    try:
        from .modules.glance.eyes_host import shutdown as eyes_off
        eyes_off()
    except Exception:
        pass


@app.on_event("shutdown")
def shutdown() -> None:
    try:
        from .modules.codewatch.router import release as codewatch_release
        codewatch_release()
    except Exception:
        pass
    try:
        from .modules.harness.service import release as harness_release
        harness_release()
    except Exception:
        pass
    _release_glance()
    try:
        from .services import ledger
        ledger.stop()
    except Exception:
        pass
    proc_reap.shutdown_workers()
    proc_reap.reap_children()


@app.get("/api/health")
def health():
    return {"ok": True}
