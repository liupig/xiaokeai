"""把动作包自带的 BGM 拷进 assets/audio，并写入对应动作的 meta.bgm。"""
import json
import shutil
import sys
from pathlib import Path

from sqlmodel import Session, create_engine, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models import Asset
from app.paths import AUDIO_DIR, DB_PATH

ROOT = Path(__file__).resolve().parents[3]
DL = ROOT / "_dl"

# 原配布包里的音频 -> 仓库内稳定文件名 -> 要绑定的动作
PACKS = [
    {
        "src": DL / "x_maomao" / "kici ki 左右猫猫摇给力嘎嘎BGM.wav",
        "dest": "maomao-yao.wav",
        "motions": ["maomao-yao.vmd"],
    },
    {
        "src": DL / "x_qbing" / "bgm.wav",
        "dest": "q-bing-yao.wav",
        "motions": ["q-bing-yao.vmd"],
    },
    {
        "src": DL / "x_taitui" / "BGM.wav",
        "dest": "taitui-dance.wav",
        "motions": ["taitui-dance.vmd"],
    },
]


def bind(session: Session, name: str, rel: str) -> bool:
    asset = session.exec(select(Asset).where(Asset.kind == "motion", Asset.name == name)).first()
    if not asset:
        print("  miss motion", name)
        return False
    try:
        meta = json.loads(asset.meta or "{}")
    except json.JSONDecodeError:
        meta = {}
    if (meta.get("category") or "") != "dance":
        print("  skip non-dance", name)
        return False
    if meta.get("bgm") == rel:
        print("  keep", name, "->", rel)
        return False
    meta["bgm"] = rel
    asset.meta = json.dumps(meta, ensure_ascii=False)
    session.add(asset)
    print("  bind", name, "->", rel)
    return True


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}")
    changed = 0
    with Session(engine) as s:
        for pack in PACKS:
            src: Path = pack["src"]
            dest = AUDIO_DIR / pack["dest"]
            if not src.exists():
                print("skip missing", src)
                continue
            shutil.copy2(src, dest)
            rel = dest.relative_to(AUDIO_DIR.parent).as_posix()
            print("copied", src.name, "->", rel, dest.stat().st_size)
            for name in pack["motions"]:
                if bind(s, name, rel):
                    changed += 1
        if changed:
            s.commit()
    print("updated", changed)


if __name__ == "__main__":
    main()
