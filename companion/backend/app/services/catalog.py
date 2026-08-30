"""资产编目：扫描 assets/ 目录，把模型与动作登记进数据库。"""
import json
import re
from pathlib import Path
from typing import List, Optional

from sqlmodel import Session, select

from ..models import Asset
from ..paths import ASSETS_DIR, AUDIO_DIR, CAMERAS_DIR, MODELS_DIR, MOTIONS_DIR

# 动作类别：用于面板分组和 LLM 选动作
CATEGORY_LABELS = {
    "idle": "待机",
    "greet": "打招呼",
    "interact": "互动",
    "dance": "舞蹈",
}
VALID_CATEGORIES = tuple(CATEGORY_LABELS.keys())
_LABEL_PREFIX_RE = re.compile(r"^\[(?:待机|打招呼|互动|舞蹈|特写|环绕|推拉|定镜|电影)\]\s*")

_CATEGORY_KEYWORDS = {
    "idle": ("待机", "待機", "闲置", "站立待机", "站姿", "idle pose", "breath", "姿势 pose", "艾尔海森姿势"),
    "greet": ("打招呼", "挥手", "招手", "问好", "问候", "挨拶", "wave", "hello",
              "再见", "手を振る", "挥手再见", "摆手", "举手"),
    "interact": ("互动", "比心", "飞吻", "害羞", "思考", "托腮", "叉腰", "点头",
                 "摇头", "鼓掌", "指向", "歪头", "伸懒腰", "坐下", "坐姿", "说话",
                 "聊天", "拥抱", "邀请", "卖萌", "撩人", "偷看", "鞠躬", "お辞儀",
                 "ポーズ", "手势", "比耶", "wink", "亲吻", "来这边",
                 "摸摸", "回头", "转身", "蹲坐", "抱膝", "摊手", "拒绝", "郁闷",
                 "格挡", "捂胸", "前倾", "眨眼", "轻拍", "病娇", "插腰", "走路", "walk",
                 "叽里呱啦"),
}


def classify_motion(text: str) -> str:
    """根据文件名/作品名判断动作类别；对不上的默认舞蹈（兼容旧资源）。"""
    if not text:
        return "dance"
    # (G)I-DLE 歌名容易误伤 idle
    blob = re.sub(r"(?i)g[- ]?idle|\(g\)-?idle", " ", text)
    lower = blob.lower()
    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in lower or kw in blob:
                return cat
    return "dance"


def strip_category_prefix(label: str) -> str:
    return _LABEL_PREFIX_RE.sub("", label or "").strip()


def apply_category(asset: Asset, category: str) -> None:
    """写入 meta.category，并给标签加上 [待机] 这类前缀。"""
    if category not in CATEGORY_LABELS:
        category = "dance"
    meta = {}
    try:
        meta = json.loads(asset.meta or "{}")
    except json.JSONDecodeError:
        meta = {}
    meta["category"] = category
    asset.meta = json.dumps(meta, ensure_ascii=False)
    base = strip_category_prefix(asset.label or asset.name)
    cn = CATEGORY_LABELS[category]
    asset.label = f"[{cn}] {base}" if cn not in base else base


def recategorize_all(session: Session) -> int:
    """按文件名/标签重新归纳已有动作。返回更新条数。"""
    n = 0
    for asset in session.exec(select(Asset).where(Asset.kind == "motion")).all():
        cat = classify_motion(f"{strip_category_prefix(asset.label)} {asset.name}")
        old = ""
        try:
            old = json.loads(asset.meta or "{}").get("category") or ""
        except json.JSONDecodeError:
            old = ""
        if old != cat or not asset.label.startswith("["):
            apply_category(asset, cat)
            session.add(asset)
            n += 1
    if n:
        session.commit()
    return n


def unbind_nondance_bgm(session: Session) -> int:
    """待机 / 打招呼 / 互动动作去掉配乐，只留舞蹈的 BGM。"""
    n = 0
    for asset in session.exec(select(Asset).where(Asset.kind == "motion")).all():
        try:
            meta = json.loads(asset.meta or "{}")
        except json.JSONDecodeError:
            continue
        if not meta.get("bgm"):
            continue
        cat = meta.get("category") or classify_motion(
            f"{strip_category_prefix(asset.label)} {asset.name}")
        if cat == "dance":
            continue
        meta.pop("bgm", None)
        asset.meta = json.dumps(meta, ensure_ascii=False)
        session.add(asset)
        n += 1
    if n:
        session.commit()
    return n


def _dance_bgm_names(session: Session) -> set:
    """当前仍被舞蹈动作引用的音频文件名（小写）。"""
    used: set = set()
    for asset in session.exec(select(Asset).where(Asset.kind == "motion")).all():
        try:
            meta = json.loads(asset.meta or "{}")
        except json.JSONDecodeError:
            continue
        if (meta.get("category") or "") != "dance":
            continue
        bgm = meta.get("bgm")
        if isinstance(bgm, str) and bgm.strip():
            used.add(Path(bgm).name.lower())
    return used


def purge_unreferenced_audio(session: Session) -> int:
    """删除没有舞蹈动作引用的音频文件（非舞蹈动作包留下的配乐）。"""
    used = _dance_bgm_names(session)
    if not AUDIO_DIR.exists():
        return 0
    n = 0
    for f in AUDIO_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name.lower() in used:
            continue
        f.unlink(missing_ok=True)
        n += 1
    return n


CAMERA_LABELS = {
    "close": "特写",
    "orbit": "环绕",
    "dolly": "推拉",
    "cut": "定镜",
    "cinematic": "电影",
    "dance": "舞蹈",
}
VALID_CAMERA_CATEGORIES = tuple(CAMERA_LABELS.keys())

_CAMERA_KEYWORDS = {
    "close": ("特写", "近景", "close", "顔", "アップ"),
    "orbit": ("环绕", "回转", "周转", "orbit", "周回", "回転"),
    "dolly": ("推拉", "推进", "拉远", "dolly", "ズーム"),
    "cinematic": ("电影", "运镜", "ドラマ", "映画", "cinematic", "crane", "螺旋"),
    "dance": ("舞蹈镜头", "舞蹈运镜", "カメラモーション"),
}


def classify_camera(text: str) -> str:
    blob = text or ""
    lower = blob.lower()
    for cat, kws in _CAMERA_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in lower or kw in blob:
                return cat
    if any(k in blob for k in ("全身", "半身", "定镜", "仰拍", "俯拍")):
        return "cut"
    return "cinematic"


def apply_camera_category(asset: Asset, category: str) -> None:
    if category not in CAMERA_LABELS:
        category = "cinematic"
    meta = {}
    try:
        meta = json.loads(asset.meta or "{}")
    except json.JSONDecodeError:
        meta = {}
    meta["category"] = category
    asset.meta = json.dumps(meta, ensure_ascii=False)
    base = strip_category_prefix(asset.label or asset.name)
    cn = CAMERA_LABELS[category]
    asset.label = f"[{cn}] {base}"


# 内置动作的中文标签（迁移自旧 motions.json）
MOTION_LABELS = {
    "gokuraku-jodo.vmd": "极乐净土",
    "gokuraku-jodo-2p.vmd": "极乐净土（2P位）",
    "maomao-yao.vmd": "左右猫猫摇（抖音热门）",
    "q-bing-yao.vmd": "q冰摇（抖音热门）",
    "taitui-dance.vmd": "抬腿舞（抖音热门）",
    "longxu-yao.vmd": "扭胯龙须摇（抖音热门）",
    "niukua-dance.vmd": "轻奢扭胯舞3.0（抖音热门）",
    "world-is-mine.vmd": "World is Mine",
    "electric-angel.vmd": "电气天使 Electric Angel",
    "freely-tomorrow.vmd": "Freely Tomorrow",
    "odds-and-ends.vmd": "Odds & Ends",
    "sharing-the-world.vmd": "Sharing The World",
    "dance.vmd": "示例舞蹈",
    "walk.vmd": "走路",
}

MODEL_LABELS = {
    "qingxiao": "清宵（国风御姐）",
}

MODEL_EXTS = {".pmx", ".vrm", ".glb"}


def _rel(p: Path) -> str:
    return p.relative_to(ASSETS_DIR).as_posix()


def _get_by_name(session: Session, kind: str, name: str) -> Optional[Asset]:
    return session.exec(
        select(Asset).where(Asset.kind == kind, Asset.name == name)
    ).first()


def register_model(session: Session, file: Path, source: str = "local",
                   source_url: str = "", label: str = "") -> Optional[Asset]:
    """登记一个模型主文件。PMX 以目录名为资产名，VRM/GLB 以文件名。"""
    if file.suffix.lower() not in MODEL_EXTS:
        return None
    if file.suffix.lower() == ".pmx":
        name = file.parent.name if file.parent != MODELS_DIR else file.stem
    else:
        name = file.stem
    existing = _get_by_name(session, "model", name)
    if existing:
        return existing
    asset = Asset(
        kind="model", name=name,
        label=label or MODEL_LABELS.get(name, name),
        path=_rel(file), fmt=file.suffix.lower().lstrip("."),
        size=file.stat().st_size, source=source, source_url=source_url,
    )
    session.add(asset)
    return asset


def register_motion(session: Session, file: Path, source: str = "local",
                    source_url: str = "", label: str = "",
                    meta: Optional[dict] = None) -> Optional[Asset]:
    if file.suffix.lower() != ".vmd":
        return None
    name = file.name
    existing = _get_by_name(session, "motion", name)
    if existing:
        return existing
    meta = dict(meta or {})
    if "category" not in meta or meta.get("category") not in CATEGORY_LABELS:
        meta["category"] = classify_motion(f"{label} {file.stem}")
    display = label or MOTION_LABELS.get(name, file.stem)
    cat_cn = CATEGORY_LABELS.get(meta.get("category") or "", "")
    if cat_cn and cat_cn not in display:
        display = f"[{cat_cn}] {display}"
    asset = Asset(
        kind="motion", name=name,
        label=display,
        path=_rel(file), fmt="vmd",
        size=file.stat().st_size, source=source, source_url=source_url,
        meta=json.dumps(meta, ensure_ascii=False),
    )
    session.add(asset)
    return asset


def register_camera(session: Session, file: Path, source: str = "local",
                    source_url: str = "", label: str = "",
                    meta: Optional[dict] = None) -> Optional[Asset]:
    if file.suffix.lower() != ".vmd":
        return None
    name = file.name
    existing = _get_by_name(session, "camera", name)
    if existing:
        return existing
    meta = dict(meta or {})
    if meta.get("category") not in CAMERA_LABELS:
        meta["category"] = classify_camera(f"{label} {file.stem}")
    display = label or file.stem
    cat_cn = CAMERA_LABELS.get(meta.get("category") or "", "")
    if cat_cn and not display.startswith(f"[{cat_cn}]"):
        display = f"[{cat_cn}] {display}"
    asset = Asset(
        kind="camera", name=name,
        label=display,
        path=_rel(file), fmt="vmd",
        size=file.stat().st_size, source=source, source_url=source_url,
        meta=json.dumps(meta, ensure_ascii=False),
    )
    session.add(asset)
    return asset


def ensure_builtin_cameras(session: Session) -> List[Asset]:
    """生成并登记内置运镜 VMD；顺带清掉已退役的绑景别镜头。"""
    from .vmd_camera import (
        RETIRED_BUILTIN_FILES,
        all_builtin_specs,
        builtin_meta,
        prune_retired_builtin_files,
        write_builtin_cameras,
    )
    prune_retired_builtin_files(CAMERAS_DIR)
    for name in RETIRED_BUILTIN_FILES:
        row = _get_by_name(session, "camera", name)
        if row:
            session.delete(row)
    write_builtin_cameras(CAMERAS_DIR, overwrite=True)
    created: List[Asset] = []
    for spec in all_builtin_specs():
        f = CAMERAS_DIR / str(spec["file"])
        if not f.is_file():
            continue
        info = builtin_meta(f.name)
        label = info.get("label") or f.stem
        cat = info.get("category") or "cinematic"
        existing = _get_by_name(session, "camera", f.name)
        if existing:
            existing.label = label
            apply_camera_category(existing, cat)
            session.add(existing)
            continue
        a = register_camera(
            session, f, source="seed",
            label=label,
            meta={"category": cat},
        )
        if a and a.id is None:
            created.append(a)
    return created


def scan_all(session: Session) -> List[Asset]:
    """全量扫描 assets/ 目录，登记新资产（不删除数据库中已有记录）。"""
    created: List[Asset] = []
    # 模型：一级目录里找 pmx；根目录里的 vrm/glb
    for sub in MODELS_DIR.iterdir():
        if sub.is_dir():
            pmx_files = sorted(sub.rglob("*.pmx"), key=lambda p: p.stat().st_size, reverse=True)
            if pmx_files:
                a = register_model(session, pmx_files[0])
                if a and a.id is None:
                    created.append(a)
        elif sub.suffix.lower() in MODEL_EXTS:
            a = register_model(session, sub)
            if a and a.id is None:
                created.append(a)
    # 动作
    for f in MOTIONS_DIR.glob("*.vmd"):
        a = register_motion(session, f)
        if a and a.id is None:
            created.append(a)
    created.extend(ensure_builtin_cameras(session))
    for f in CAMERAS_DIR.glob("*.vmd"):
        a = register_camera(session, f)
        if a and a.id is None:
            created.append(a)
    session.commit()
    recategorize_all(session)
    return created
