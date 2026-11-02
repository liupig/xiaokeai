"""Four-language constructed-content -> production candidate -> real LLM check."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run():
    from sqlmodel import Session, select
    from app.db import engine
    from app.models import Character
    from app.services.settings_store import get_all
    from app.locale_pack import set_reply, detect_script
    from app.modules.sight import service
    from app.modules.sight.service import bound_speech
    from app.modules.glance.situation import Situation, parse_observation
    from app.modules.glance.media_director import bind_context
    from app.modules.glance.game_director import grounded_reply
    from app.modules.glance.watch import along_turn
    from app.services.llm import SYSTEM_PROTOCOL
    from app.services.tts import language_route
    with Session(engine) as db:
        config = get_all(db)
        character = db.exec(select(Character).order_by(Character.id)).first()
        persona = character.persona if character else "You are Xiaokeai."
    cases = [
        ("zh-CN", "movie", "vlc.exe", "归途 第12集", "字幕：船就要开了，快上来"),
        ("en", "movie", "vlc.exe", "Homecoming Episode 12", "Subtitles: The ship is leaving. Come aboard."),
        ("ja", "video", "chrome.exe", "YouTube", "字幕：小さな犬が大きなクッションを引っ張っている"),
        ("ko", "music", "spotify.exe", "Spotify", "곡명: 비 오는 밤\n가수: 가수 A\n가사: 창밖에는 아직 비가 내리고 있어요"),
    ]
    result = []
    for lang, scene, process, title, content in cases:
        service.reset()
        brief = service.commit(process, title, title, content)
        offer = Situation().ingest(parse_observation(brief.handoff))
        assert offer is not None, (lang, brief)
        bind_context(offer, brief.public())
        set_reply(lang)
        messages = [{"role": "system", "content": persona + "\n" + SYSTEM_PROTOCOL},
                    {"role": "user", "content": bound_speech(along_turn(), line=offer.summary, rule=brief.speak+brief.company)}]
        reply = await grounded_reply(config["llm"], messages, evidence=offer.summary, topic=offer.topic_id, scene=scene)
        guessed = detect_script(reply["text"])
        result.append({"language": lang, "source": "constructed-contract", "summary": offer.summary, "reply": reply,
                       "detected_reply_language": guessed, "language_ok": guessed == lang,
                       "tts_route": language_route(config["tts"].get("engine", "mimo"), lang), "real_audio_tested": False})
        print(json.dumps(result[-1], ensure_ascii=False), flush=True)
    set_reply("zh-CN")
    script = Path("app/modules/sight/read_screen.ps1")
    langs = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-ListLanguages"], capture_output=True, timeout=10)
    report = {"cases": result, "installed_ocr_languages": json.loads(langs.stdout.decode("utf-8-sig"))}
    Path("data/media-eval/languages.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(row["language_ok"] and row["reply"]["action"] == "speak" for row in result)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run())
