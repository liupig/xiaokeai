"""压缩包解压与内容识别。

- zip：UTF-8 标记、GBK、Shift-JIS 文件名都能解开（模之屋常见中文 PMX）
- rar / 7z：优先用打包目录 tools/7z.exe，没有再试系统 7-Zip / tar
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from ..paths import ROOT_DIR, TMP_DIR
from .vmd_camera import is_camera_vmd

_ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f]')


def sniff_kind(path: Path) -> str:
    """看文件头判断类型，不信下载地址的后缀。"""
    head = path.read_bytes()[:32]
    if head.startswith(b"PK"):
        return ".zip"
    if head.startswith(b"Rar!") or head.startswith(b"\x52\x61\x72\x21"):
        return ".rar"
    if head.startswith(b"7z\xbc\xaf'\x1c"):
        return ".7z"
    if head.startswith(b"Vocaloid Motion Data"):
        return ".vmd"
    suf = path.suffix.lower()
    if suf in {".zip", ".rar", ".7z", ".vmd", ".vpd", ".vrm", ".glb", ".pmx"}:
        return suf
    return suf or ""


def _decode_zip_name(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb18030", "shift-jis", "cp932"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if "\ufffd" in text:
            continue
        return text
    return raw.decode("gbk", errors="replace")


def _member_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    # Python 3.11+ 可能已经按系统编码解出中文，再 encode cp437 会直接炸
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    return _decode_zip_name(raw)


def _safe_target(dest: Path, name: str) -> Optional[Path]:
    name = name.replace("\\", "/")
    parts: List[str] = []
    for part in name.split("/"):
        part = _ILLEGAL.sub("_", part).rstrip(" .")
        if not part or part in (".", ".."):
            continue
        parts.append(part)
    if not parts:
        return None
    target = (dest.joinpath(*parts)).resolve()
    root = dest.resolve()
    if target != root and root not in target.parents:
        return None
    return target


def _extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            try:
                name = _member_name(info)
                target = _safe_target(dest, name)
                if target is None:
                    continue
                if info.is_dir() or name.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
            except Exception as exc:
                print(f"[extract] skip {info.filename!r}: {exc}")


def _find_7z() -> Optional[Path]:
    cands = [ROOT_DIR / "tools" / "7z.exe"]
    packed = os.environ.get("COMPANION_ROOT")
    if packed:
        cands.append(Path(packed) / "tools" / "7z.exe")
    cands.extend([
        Path(r"D:\BingSoft\7-Zip\7z.exe"),
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ])
    which = shutil.which("7z") or shutil.which("7z.exe")
    if which:
        cands.append(Path(which))
    for p in cands:
        if p and p.is_file():
            return p
    return None


def _extract_7z(archive: Path, dest: Path) -> None:
    seven = _find_7z()
    if seven is None:
        result = subprocess.run(
            ["tar", "-xf", str(archive), "-C", str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and not any(dest.iterdir()):
            raise RuntimeError(
                "解压失败：打包目录缺少 tools/7z.exe，系统 tar 也打不开这个压缩包。"
                f" {result.stderr[:200]}"
            )
        return
    result = subprocess.run(
        [str(seven), "x", str(archive), f"-o{dest}", "-y", "-aoa"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and not any(dest.iterdir()):
        raise RuntimeError(f"7z 解压失败: {(result.stderr or result.stdout)[:300]}")


def extract_archive(archive: Path, dest: Path) -> None:
    """解压 zip/rar/7z 到 dest，处理中日文文件名。"""
    dest.mkdir(parents=True, exist_ok=True)
    kind = sniff_kind(archive)
    if kind == ".zip":
        _extract_zip(archive, dest)
        if not any(dest.rglob("*.pmx")) and not any(dest.rglob("*.vmd")) and _find_7z():
            # Python zip 仍可能丢掉条目，再用 7z 补一次
            _extract_7z(archive, dest)
        if not any(dest.iterdir()):
            raise RuntimeError("zip 解压后是空的")
        return
    if kind in (".rar", ".7z"):
        _extract_7z(archive, dest)
        return
    raise ValueError(f"不支持的压缩格式: {kind or archive.suffix}")


def classify_extracted(root: Path) -> Dict[str, object]:
    """识别解压目录内容。

    返回 {model: pmx路径|None, motions: [主舞vmd...], expression_vmds: [...],
          camera_vmds: [...], audio: [wav/mp3...]}
    """
    pmx_files = sorted(root.rglob("*.pmx"), key=lambda p: p.stat().st_size, reverse=True)
    vmds = list(root.rglob("*.vmd"))
    audio = [p for ext in ("*.wav", "*.mp3", "*.ogg") for p in root.rglob(ext)]

    motions: List[Path] = []
    cameras: List[Path] = []
    expressions: List[Path] = []
    for v in vmds:
        lower = v.name.lower()
        if is_camera_vmd(v):
            cameras.append(v)
        elif (any(k in v.name for k in ("表情", "リップ", "口型", "モーフ", "面部"))
              or "face" in lower or "lip" in lower or "morph" in lower
              or "facial" in lower):
            expressions.append(v)
        else:
            motions.append(v)

    return {
        "model": pmx_files[0] if pmx_files else None,
        "motions": sorted(motions, key=lambda p: p.stat().st_size, reverse=True),
        "camera_vmds": cameras,
        "expression_vmds": expressions,
        "audio": audio,
    }


def make_tmp_dir(name: str) -> Path:
    d = TMP_DIR / name
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d
