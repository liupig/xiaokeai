"""把 D:\\BingLoads 今天下载的动作批量导入资产库。

- 单文件 vmd/vpd 与 zip/rar 包统一走 importer.import_downloaded
- 每个条目显式给中文标签；必要时强制 category（idle/greet/interact/dance）
- 跳过重复下载（文件名带 " (1)"）
"""
import sys
from pathlib import Path

from sqlmodel import Session, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.paths import DB_PATH
from app.services.importer import import_downloaded

SRC = Path(r"D:\BingLoads")


def pick(prefix: str) -> Path:
    """按文件名前缀在下载目录里找唯一文件（忽略哈希后缀）。"""
    hits = [p for p in SRC.iterdir()
            if p.is_file() and p.name.startswith(prefix) and " (1)" not in p.name]
    if not hits:
        raise FileNotFoundError(prefix)
    return hits[0]


# (文件前缀, 展示标签, 强制类别或 None)
ITEMS = [
    # ---- 散件 VMD ----
    ("JS_by_", "JS 舞蹈（芝麻凛配布）", "dance"),
    ("叉腰_by_paomian24324", "叉腰（泡面配布）", "interact"),
    ("思考_by_", "思考（快乐小孩配布）", "interact"),
    ("打招呼_by_", "打招呼（缘分的天空配布）", "greet"),
    ("抱胸思考姿势_by_", "抱胸思考", "interact"),
    ("挥手_by_", "挥手（JONG配布）", "greet"),
    ("红叶谷希美 转身动作", "转身（右）", "interact"),
    # ---- 姿势 VPD（自动转 VMD）----
    ("pose1_by_", "姿势 Pose1（KStarLDust配布）", "interact"),
    ("叉腰_by_崩坏", "叉腰姿势（崩坏世界配布）", "interact"),
    ("可爱的打招呼_by_", "可爱的打招呼姿势", "greet"),
    ("艾尔海森_by_", "艾尔海森姿势（苑工配布）", "interact"),
    ("迪奥娜叉腰_by_", "迪奥娜叉腰姿势", "interact"),
    # ---- 动作包 ----
    ("1.0 _by_", "孔蚊银钱配布动作", "dance"),
    ("bro懂我的品味_by_", "bro懂我的品味（梗舞）", "dance"),
    ("原神少女剧情用", "原神少女剧情动作", "interact"),
    ("原神成男剧情用", "原神成男剧情动作", "interact"),
    ("叉腰_by_独眼君", "叉腰（独眼君配布）", "interact"),
    ("叽里呱啦说什么呢_by_", "叽里呱啦说什么呢（说话动作）", "interact"),
    ("哈基米南北绿豆动作_by_", "哈基米南北绿豆（梗舞）", "dance"),
    ("宝宝我想告诉你_by_", "宝宝我想告诉你", "dance"),
    ("害羞摇_by_", "害羞摇", "dance"),
    ("害羞的miku1.1_by_", "害羞的miku", "interact"),
    ("害羞表白舞_by_", "害羞表白舞", "dance"),
    ("已经有我啦_by_", "已经有我啦", "dance"),
    ("心动是你动作_by_", "心动是你", "dance"),
    ("扶桌摇_by_", "扶桌摇", "dance"),
    ("抖肩舞_by_", "抖肩舞", "dance"),
    ("旦那様とのラブラブ", "旦那様とのラブラブ・ラブソング", "dance"),
    ("蘑菇蘑菇 by", "蘑菇蘑菇（梗舞）", "dance"),
    ("配布_by_Parim", "Parim配布小动作", "interact"),
    ("鼙鼓摇_by_", "鼙鼓摇", "dance"),
    ("点头yes摇头no猫猫摇", "点头yes摇头no猫猫摇", "interact"),
]


def main():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    total = 0
    with Session(engine) as s:
        for prefix, label, cat in ITEMS:
            try:
                src = pick(prefix)
            except FileNotFoundError:
                print(f"MISS  {prefix}")
                continue
            meta = {"category": cat} if cat else None
            try:
                created = import_downloaded(s, src, source="local", label=label,
                                            extra_meta=meta)
            except Exception as e:
                print(f"ERR   {label}: {e}")
                continue
            total += len(created)
            for a in created:
                print(f"OK    [{a.kind}] {a.label}  ->  {a.name}")
    print(f"\nimported {total} assets")


if __name__ == "__main__":
    main()
