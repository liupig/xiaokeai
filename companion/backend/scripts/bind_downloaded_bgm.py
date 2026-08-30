"""把 music-api/downloads 里已下好的歌拷进 assets/audio 并绑定到舞蹈。"""
import json
import shutil
import sys
from pathlib import Path

from sqlmodel import Session, create_engine, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import Asset
from app.paths import AUDIO_DIR, DB_PATH

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "music-api" / "downloads"

PACKS = [
    {"src": "极乐净土 - GARNiDELiA.m4a", "dest": "gokuraku-jodo.m4a",
     "motions": ["gokuraku-jodo.vmd", "gokuraku-jodo-2p.vmd"]},
    {"src": "电气天使 Electric Angel.m4a", "dest": "electric-angel.m4a",
     "motions": ["electric-angel.vmd"]},
    {"src": "Freely Tomorrow - Mitchie M.m4a", "dest": "freely-tomorrow.m4a",
     "motions": ["freely-tomorrow.vmd"]},
    {"src": "World is Mine - supercell.m4a", "dest": "world-is-mine.m4a",
     "motions": ["world-is-mine.vmd"]},
    {"src": "Odds & Ends - ryo supercell.m4a", "dest": "odds-and-ends.m4a",
     "motions": ["odds-and-ends.vmd"]},
    {"src": "Sharing The World - BIGHEAD.m4a", "dest": "sharing-the-world.m4a",
     "motions": ["sharing-the-world.vmd"]},
    {"src": "浪沫起舞 - HOYO-MiX.m4a", "dest": "eula-langmo.m4a",
     "motions": ["eula-v3.vmd"]},
]


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}")
    changed = 0
    with Session(engine) as s:
        for pack in PACKS:
            src = SRC / pack["src"]
            dest = AUDIO_DIR / pack["dest"]
            if not src.exists():
                print("skip missing", src)
                continue
            shutil.copy2(src, dest)
            rel = dest.relative_to(AUDIO_DIR.parent).as_posix()
            print("copied", pack["src"], "->", rel, dest.stat().st_size)
            for name in pack["motions"]:
                a = s.exec(select(Asset).where(Asset.kind == "motion", Asset.name == name)).first()
                if not a:
                    print("  miss motion", name)
                    continue
                try:
                    meta = json.loads(a.meta or "{}")
                except json.JSONDecodeError:
                    meta = {}
                if (meta.get("category") or "") != "dance":
                    print("  skip non-dance", name)
                    continue
                if meta.get("bgm") != rel:
                    meta["bgm"] = rel
                    a.meta = json.dumps(meta, ensure_ascii=False)
                    s.add(a)
                    changed += 1
                print("  bind", name, "->", rel)
        if changed:
            s.commit()
    print("updated", changed)


if __name__ == "__main__":
    main()
