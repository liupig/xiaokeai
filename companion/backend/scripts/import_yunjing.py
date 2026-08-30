"""把 E:\\BingCode\\bingGames\\yunjing 里的运镜压缩包导入资产库。"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.paths import DB_PATH  # noqa: E402
from app.services.importer import import_downloaded  # noqa: E402

SRC = Path(r"E:\BingCode\bingGames\yunjing")

# (文件名前缀, 展示标签, 镜头类别)
ITEMS = [
    ("妄想天使之舞", "妄想天使之舞 镜头", "cinematic"),
]


def pick(prefix: str) -> Path:
    hits = [p for p in SRC.iterdir() if p.is_file() and p.name.startswith(prefix)]
    if not hits:
        raise FileNotFoundError(prefix)
    return hits[0]


def main() -> None:
    engine = create_engine(f"sqlite:///{DB_PATH}")
    total = 0
    with Session(engine) as s:
        for prefix, label, cat in ITEMS:
            try:
                src = pick(prefix)
            except FileNotFoundError:
                print(f"MISS  {prefix}")
                continue
            print(f"\n>> {src.name}")
            try:
                created = import_downloaded(
                    s, src, source="local", label=label,
                    extra_meta={"category": cat},
                )
            except Exception as exc:  # noqa: BLE001
                print(f"ERR   {label}: {exc}")
                continue
            total += len(created)
            for a in created:
                print(f"OK    [{a.kind}] {a.label}  ->  {a.name}  ({a.size})")
    print(f"\nimported {total} assets")


if __name__ == "__main__":
    main()
