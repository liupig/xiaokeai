"""镜头 VMD：识别、生成内置运镜。

VMD 镜头关键帧（61 字节）：
  frame uint32, distance float, pos xyz, rot xyz（弧度）,
  interpolation 24B, fov uint32, perspective uint8
"""
from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

# 接近线性的镜头补间（6 条曲线 × ax,ay,bx,by）
_CAM_INTERP = bytes([
    20, 20, 20, 20, 20, 20,
    20, 20, 20, 20, 20, 20,
    107, 107, 107, 107, 107, 107,
    107, 107, 107, 107, 107, 107,
])


def _sjis(text: str, size: int) -> bytes:
    raw = text.encode("shift_jis", errors="replace")[:size]
    return raw + b"\x00" * (size - len(raw))


def inspect_vmd(path: Path) -> Dict[str, int]:
    """读 VMD 头部计数：骨骼 / 表情 / 镜头关键帧数量。"""
    data = path.read_bytes()
    if len(data) < 54:
        return {"bones": 0, "morphs": 0, "cameras": 0}
    off = 50  # 30 magic + 20 model name
    n_bones = struct.unpack_from("<I", data, off)[0]
    off += 4 + max(n_bones, 0) * 111
    if off + 4 > len(data):
        return {"bones": n_bones, "morphs": 0, "cameras": 0}
    n_morphs = struct.unpack_from("<I", data, off)[0]
    off += 4 + max(n_morphs, 0) * 23
    if off + 4 > len(data):
        return {"bones": n_bones, "morphs": n_morphs, "cameras": 0}
    n_cams = struct.unpack_from("<I", data, off)[0]
    return {"bones": n_bones, "morphs": n_morphs, "cameras": n_cams}


def is_camera_vmd(path: Path, name_hint: str = "") -> bool:
    """文件名或内容判定为镜头 VMD。纯镜头文件（无骨骼、有镜头帧）优先。"""
    blob = f"{name_hint} {path.name}"
    lower = blob.lower()
    if any(k in blob for k in ("镜头", "カメラ", "相机")) or "camera" in lower:
        return True
    try:
        info = inspect_vmd(path)
    except (OSError, struct.error):
        return False
    return info["cameras"] > 0 and info["bones"] == 0


CamKey = Tuple[int, float, Tuple[float, float, float], Tuple[float, float, float], int]


def _pack_key(frame: int, distance: float, pos: Sequence[float],
              rot: Sequence[float], fov: int = 30) -> bytes:
    return (
        struct.pack("<I", frame)
        + struct.pack("<f", distance)
        + struct.pack("<fff", pos[0], pos[1], pos[2])
        + struct.pack("<fff", rot[0], rot[1], rot[2])
        + _CAM_INTERP
        + struct.pack("<I", fov)
        + struct.pack("<B", 0)
    )


def build_camera_vmd(keys: List[CamKey], model_name: str = "カメラ・照明") -> bytes:
    out = bytearray()
    out += _sjis("Vocaloid Motion Data 0002", 30)
    out += _sjis(model_name, 20)
    out += struct.pack("<I", 0)  # bones
    out += struct.pack("<I", 0)  # morphs
    out += struct.pack("<I", len(keys))
    for frame, dist, pos, rot, fov in keys:
        out += _pack_key(frame, dist, pos, rot, fov)
    out += struct.pack("<I", 0)  # lights
    return bytes(out)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _sample_path(n: int, duration: int, fn) -> List[CamKey]:
    keys: List[CamKey] = []
    for i in range(n + 1):
        t = i / n
        frame = int(duration * t)
        keys.append(fn(t, frame))
    return keys


# 已退役：绑死景别或和程序化运镜重复的内置镜头。启动时删文件和资产记录。
RETIRED_BUILTIN_FILES = (
    "cam-full.vmd", "cam-half.vmd", "cam-close.vmd",
    "cam-low.vmd", "cam-high.vmd",
    "cam-dolly-in.vmd", "cam-dolly-out.vmd",
    "cam-crane.vmd", "cam-low-push.vmd", "cam-breathe.vmd",
)


def _orbit_keys(yaw_from: float, yaw_to: float, dist: float, y: float,
                duration: int = 120, n: int = 8) -> List[CamKey]:
    def fn(t: float, frame: int) -> CamKey:
        yaw = _lerp(yaw_from, yaw_to, t)
        return (frame, dist, (0.0, y, 0.0), (0.0, yaw, 0.0), 30)
    return _sample_path(n, duration, fn)


# 镜头库只留「从哪看 / 怎么连续看」。定镜走程序化 hold，景别不写进 VMD。
# MMD 单位：角色身高约 20。本项目模型缩放 0.08，镜头播放时同步缩放。
BUILTINS: List[Dict[str, object]] = [
    {
        "file": "cam-orbit-l.vmd", "label": "左侧环绕", "category": "orbit",
        "keys": _orbit_keys(0.15, -0.85, -26.0, 13.0, 100, 8),
    },
    {
        "file": "cam-orbit-r.vmd", "label": "右侧环绕", "category": "orbit",
        "keys": _orbit_keys(-0.15, 0.85, -26.0, 13.0, 100, 8),
    },
    {
        "file": "cam-orbit-360.vmd", "label": "环绕一周", "category": "orbit",
        "keys": _orbit_keys(0.0, math.tau, -28.0, 12.5, 240, 16),
    },
    {
        "file": "cam-spiral.vmd", "label": "螺旋一周", "category": "cinematic",
        "keys": _sample_path(16, 200, lambda t, f: (
            f, -28.0,
            (0.0, _lerp(10.0, 15.5, t), 0.0),
            (_lerp(0.04, -0.1, t), t * math.tau, 0.0), 30,
        )),
    },
    {
        "file": "cam-arc.vmd", "label": "弧线扫过", "category": "orbit",
        "keys": _orbit_keys(-0.7, 0.7, -24.0, 13.5, 110, 8),
    },
]


def all_builtin_specs() -> List[Dict[str, object]]:
    return list(BUILTINS)


def write_builtin_cameras(dest_dir: Path, overwrite: bool = False) -> List[Path]:
    """把内置运镜写成 VMD 文件。默认已存在则跳过；overwrite 时重写路径内容。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for spec in all_builtin_specs():
        path = dest_dir / str(spec["file"])
        if path.exists() and not overwrite:
            continue
        path.write_bytes(build_camera_vmd(spec["keys"]))  # type: ignore[arg-type]
        written.append(path)
    return written


def prune_retired_builtin_files(dest_dir: Path) -> List[Path]:
    """删掉已退役的内置 VMD。返回实际删掉的路径。"""
    removed: List[Path] = []
    for name in RETIRED_BUILTIN_FILES:
        path = dest_dir / name
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def builtin_meta(filename: str) -> Dict[str, str]:
    for spec in all_builtin_specs():
        if spec["file"] == filename:
            return {"label": str(spec["label"]), "category": str(spec["category"])}
    return {}
