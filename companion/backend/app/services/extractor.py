"""压缩包解压与内容识别。

- zip：优先 UTF-8，失败按 GBK(936)/Shift-JIS(932) 解码文件名
- rar：调用 Windows 自带 bsdtar（tar.exe）
- 解压后自动识别：PMX 主模型 / VMD 分类（主舞、表情、镜头）/ BGM 音频
"""
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from ..paths import TMP_DIR
from .vmd_camera import is_camera_vmd


def _decode_zip_name(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "shift-jis"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def extract_archive(archive: Path, dest: Path) -> None:
    """解压 zip/rar 到 dest，处理中日文文件名乱码。"""
    dest.mkdir(parents=True, exist_ok=True)
    suffix = archive.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                # zipfile 默认用 cp437 解码非 UTF-8 标记的文件名，还原原始字节再猜编码
                if info.flag_bits & 0x800:
                    name = info.filename
                else:
                    name = _decode_zip_name(info.filename.encode("cp437"))
                target = dest / name
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    elif suffix in (".rar", ".7z"):
        # Windows 10+ 自带 bsdtar，支持 rar/7z 读取
        result = subprocess.run(
            ["tar", "-xf", str(archive), "-C", str(dest)],
            capture_output=True, text=True,
        )
        # bsdtar 对个别损坏条目（如截断的 wav）会报错但主体文件已解出，只在完全没输出文件时抛错
        if result.returncode != 0 and not any(dest.iterdir()):
            raise RuntimeError(f"解压失败: {result.stderr[:300]}")
    else:
        raise ValueError(f"不支持的压缩格式: {suffix}")


def classify_extracted(root: Path) -> Dict[str, object]:
    """识别解压目录内容。

    返回 {model: pmx路径|None, motions: [主舞vmd...], expression_vmds: [...],
          camera_vmds: [...], audio: [wav/mp3...]}
    VMD 分类规则：文件名含 镜头/カメラ/camera，或文件本身只有镜头关键帧 → 镜头；
    含 表情/リップ/face → 表情；其余一律视为主动作。
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
