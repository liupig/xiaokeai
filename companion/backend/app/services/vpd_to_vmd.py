"""把 VPD 姿势转成可循环播放的短 VMD（两帧保持同一姿势）。"""
from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import List, Tuple

# VMD 默认补间（接近线性）
_INTERP = bytes([
    20, 20, 20, 20, 20, 20, 20, 20, 107, 107, 107, 107, 107, 107, 107, 107,
] * 4)


def _sjis(text: str, size: int) -> bytes:
    raw = text.encode("shift_jis", errors="replace")[:size]
    return raw + b"\x00" * (size - len(raw))


def parse_vpd(data: bytes) -> List[Tuple[str, Tuple[float, float, float], Tuple[float, float, float, float]]]:
    """返回 [(bone_name, (x,y,z), (qx,qy,qz,qw)), ...]"""
    text = data.decode("shift_jis", errors="replace")
    bones = []
    pattern = re.compile(
        r"Bone\d+\s*\{\s*([^\r\n]+)\r?\n\s*"
        r"([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*;[^\r\n]*\r?\n\s*"
        r"([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*;",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        pos = (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        rot = (float(m.group(5)), float(m.group(6)), float(m.group(7)), float(m.group(8)))
        bones.append((name, pos, rot))
    return bones


def vpd_to_vmd_bytes(vpd: bytes, hold_frames: int = 60) -> bytes:
    bones = parse_vpd(vpd)
    if not bones:
        raise ValueError("VPD 里没有解析到骨骼")
    out = bytearray()
    out += _sjis("Vocaloid Motion Data 0002", 30)
    out += _sjis("vpd_pose", 20)
    # 每个骨骼写 0 帧和 hold 帧，形成可循环的静止姿势
    count = len(bones) * 2
    out += struct.pack("<I", count)
    for frame in (0, hold_frames):
        for name, pos, rot in bones:
            out += _sjis(name, 15)
            out += struct.pack("<I", frame)
            out += struct.pack("<fff", *pos)
            out += struct.pack("<ffff", *rot)
            out += _INTERP
    out += struct.pack("<I", 0)  # morph
    out += struct.pack("<I", 0)  # camera
    out += struct.pack("<I", 0)  # light
    return bytes(out)


def convert_file(src: Path, dest: Path) -> Path:
    data = src.read_bytes()
    dest.write_bytes(vpd_to_vmd_bytes(data))
    return dest
