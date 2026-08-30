"""把压缩包 / 单文件导入资产仓库并入库。"""
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from sqlmodel import Session

from ..models import Asset
from ..paths import AUDIO_DIR, CAMERAS_DIR, MODELS_DIR, MOTIONS_DIR
from . import catalog
from .extractor import classify_extracted, extract_archive, make_tmp_dir
from .vmd_camera import is_camera_vmd


def _safe_name(name: str) -> str:
    """生成 ASCII 安全的文件/目录名，保留中文（浏览器/后端都支持 UTF-8 路径），
    只去掉危险字符。"""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned or uuid.uuid4().hex[:8]


def _unique_dest(folder: Path, stem: str) -> Path:
    dest = folder / f"{stem}.vmd"
    idx = 1
    while dest.exists():
        idx += 1
        dest = folder / f"{stem}_{idx}.vmd"
    return dest


def _register_cameras(session: Session, files: List[Path], source: str,
                      source_url: str, base_label: str,
                      extra_meta: Optional[dict]) -> List[Asset]:
    created: List[Asset] = []
    for vmd in files:
        stem = _safe_name(vmd.stem)
        dest = _unique_dest(CAMERAS_DIR, stem)
        shutil.copy2(vmd, dest)
        meta = dict(extra_meta or {})
        forced = (extra_meta or {}).get("category")
        if forced not in catalog.CAMERA_LABELS:
            meta["category"] = catalog.classify_camera(f"{base_label} {vmd.stem}")
        cam_label = (base_label if len(files) == 1
                     else f"{base_label} · {vmd.stem}")
        a = catalog.register_camera(session, dest, source=source,
                                    source_url=source_url, label=cam_label, meta=meta)
        if a:
            created.append(a)
    return created


def import_archive(session: Session, archive: Path, source: str = "local",
                   source_url: str = "", label: str = "",
                   extra_meta: Optional[dict] = None) -> List[Asset]:
    """解压压缩包，识别内容，移动到资产仓库并登记。返回新登记的资产。"""
    work = make_tmp_dir(f"import_{uuid.uuid4().hex[:8]}")
    extract_archive(archive, work)
    # 姿势文件转成可播放的短 VMD，再走统一分类
    from .vpd_to_vmd import convert_file
    for vpd in list(work.rglob("*.vpd")):
        try:
            convert_file(vpd, vpd.with_suffix(".vmd"))
        except Exception:
            continue
    info = classify_extracted(work)
    created: List[Asset] = []
    base_label = label or _safe_name(archive.stem)

    model_file = info["model"]
    if model_file is not None:
        # 模型：整个所在目录（含贴图）搬进 models/<名字>/
        src_dir = model_file.parent
        dir_name = _safe_name(base_label if src_dir == work else src_dir.name)
        dest_dir = MODELS_DIR / dir_name
        idx = 1
        while dest_dir.exists():
            idx += 1
            dest_dir = MODELS_DIR / f"{dir_name}_{idx}"
        shutil.copytree(src_dir, dest_dir)
        pmx_in_dest = dest_dir / model_file.relative_to(src_dir)
        a = catalog.register_model(session, pmx_in_dest, source=source,
                                   source_url=source_url, label=base_label)
        if a:
            created.append(a)

    # 动作：主舞 vmd 逐个搬进 motions/。配乐只留给舞蹈，待机/打招呼/互动不拷、不绑。
    planned: List[tuple] = []
    for vmd in info["motions"]:
        meta = dict(extra_meta or {})
        # 合集里按单文件名再细分；单作品若文件名看不出类别，沿用搜索时的类别
        file_cat = catalog.classify_motion(f"{base_label} {vmd.stem}")
        forced = (extra_meta or {}).get("category")
        if file_cat != "dance":
            meta["category"] = file_cat
        elif forced in ("idle", "greet", "interact"):
            meta["category"] = forced
        else:
            meta["category"] = file_cat
        motion_label = (base_label if len(info["motions"]) == 1
                        else f"{base_label} · {vmd.stem}")
        planned.append((vmd, meta, motion_label))

    audio_files = info["audio"]
    bgm_rel = ""
    if audio_files and any(m.get("category") == "dance" for _, m, _ in planned):
        bgm = max(audio_files, key=lambda p: p.stat().st_size)
        bgm_dest = AUDIO_DIR / f"{_safe_name(base_label)}_{_safe_name(bgm.name)}"
        shutil.copy2(bgm, bgm_dest)
        bgm_rel = bgm_dest.relative_to(AUDIO_DIR.parent).as_posix()

    for vmd, meta, motion_label in planned:
        stem = _safe_name(vmd.stem)
        dest = MOTIONS_DIR / f"{stem}.vmd"
        idx = 1
        while dest.exists():
            idx += 1
            dest = MOTIONS_DIR / f"{stem}_{idx}.vmd"
        shutil.copy2(vmd, dest)
        if bgm_rel and meta.get("category") == "dance":
            meta["bgm"] = bgm_rel
        a = catalog.register_motion(session, dest, source=source,
                                    source_url=source_url, label=motion_label, meta=meta)
        if a:
            created.append(a)

    cam_assets = _register_cameras(
        session, list(info["camera_vmds"]), source, source_url, base_label, extra_meta)
    created.extend(cam_assets)
    if cam_assets:
        cam_rel = cam_assets[0].path
        for a in created:
            if a.kind != "motion":
                continue
            try:
                meta = json.loads(a.meta or "{}")
            except json.JSONDecodeError:
                meta = {}
            if not meta.get("camera"):
                meta["camera"] = cam_rel
                a.meta = json.dumps(meta, ensure_ascii=False)
                session.add(a)

    session.commit()
    for a in created:
        session.refresh(a)
    shutil.rmtree(work, ignore_errors=True)
    return created


def import_single_file(session: Session, file: Path, source: str = "local",
                       source_url: str = "", label: str = "",
                       extra_meta: Optional[dict] = None) -> List[Asset]:
    """导入单个 .vmd / .vrm / .glb 文件。"""
    created: List[Asset] = []
    ext = file.suffix.lower()
    if ext == ".vmd":
        if is_camera_vmd(file, label):
            return _import_camera_file(session, file, source, source_url, label, extra_meta)
        stem = _safe_name(label) if label else _safe_name(file.stem)
        dest = _unique_dest(MOTIONS_DIR, stem)
        shutil.copy2(file, dest)
        meta = dict(extra_meta or {})
        if meta.get("category") not in catalog.CATEGORY_LABELS:
            meta["category"] = catalog.classify_motion(f"{label} {stem}")
        a = catalog.register_motion(session, dest, source=source,
                                    source_url=source_url, label=label, meta=meta)
    elif ext in (".vrm", ".glb"):
        dest = MODELS_DIR / _safe_name(file.name)
        shutil.copy2(file, dest)
        a = catalog.register_model(session, dest, source=source,
                                   source_url=source_url, label=label)
    else:
        raise ValueError(f"不支持的文件类型: {ext}")
    if a:
        created.append(a)
    session.commit()
    for item in created:
        session.refresh(item)
    return created


def _import_camera_file(session: Session, file: Path, source: str,
                        source_url: str, label: str,
                        extra_meta: Optional[dict]) -> List[Asset]:
    stem = _safe_name(label) if label else _safe_name(file.stem)
    dest = _unique_dest(CAMERAS_DIR, stem)
    shutil.copy2(file, dest)
    meta = dict(extra_meta or {})
    if meta.get("category") not in catalog.CAMERA_LABELS:
        meta["category"] = catalog.classify_camera(f"{label} {stem}")
    a = catalog.register_camera(session, dest, source=source,
                                source_url=source_url, label=label, meta=meta)
    created = [a] if a else []
    session.commit()
    for item in created:
        session.refresh(item)
    return created


def import_downloaded(session: Session, file: Path, source: str = "local",
                      source_url: str = "", label: str = "",
                      extra_meta: Optional[dict] = None) -> List[Asset]:
    """下载完成后的统一入口：压缩包解压入库，单个 vmd 直接登记。"""
    suffix = file.suffix.lower()
    if suffix == ".vmd":
        return import_single_file(session, file, source, source_url, label, extra_meta)
    if suffix == ".vpd":
        from .vpd_to_vmd import convert_file
        tmp_vmd = file.with_suffix(".vmd")
        convert_file(file, tmp_vmd)
        try:
            return import_single_file(session, tmp_vmd, source, source_url, label, extra_meta)
        finally:
            tmp_vmd.unlink(missing_ok=True)
    if suffix in (".zip", ".rar", ".7z"):
        return import_archive(session, file, source, source_url, label, extra_meta)
    raise ValueError(f"不支持的文件类型: {suffix}")
