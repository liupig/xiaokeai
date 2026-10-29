"""只够拆直播间推送帧的 protobuf 读写。不依赖 protoc。"""
from __future__ import annotations


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = 0
    n = 0
    while i < len(buf) and shift <= 63:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7
    raise ValueError("bad varint")


def fields(buf: bytes) -> dict[int, list]:
    """字段号 → 值。整数是 int，长度字段是 bytes。重复字段按出现顺序留在列表里。"""
    out: dict[int, list] = {}
    i = 0
    n = len(buf)
    while i < n:
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _varint(buf, i)
        elif wire == 1:
            val = buf[i:i + 8]
            i += 8
        elif wire == 2:
            ln, i = _varint(buf, i)
            val = buf[i:i + ln]
            i += ln
        elif wire == 5:
            val = buf[i:i + 4]
            i += 4
        else:
            raise ValueError(f"wire {wire}")
        out.setdefault(field, []).append(val)
    return out


def text(vals: list | None, index: int = 0) -> str:
    if not vals or index >= len(vals):
        return ""
    val = vals[index]
    if isinstance(val, bytes):
        return val.decode("utf-8", "replace")
    if isinstance(val, int):
        return str(val)
    return ""


def num(vals: list | None, index: int = 0) -> int:
    if not vals or index >= len(vals):
        return 0
    val = vals[index]
    return int(val) if isinstance(val, int) else 0


def blob(vals: list | None, index: int = 0) -> bytes:
    if not vals or index >= len(vals) or not isinstance(vals[index], bytes):
        return b""
    return vals[index]


def put_varint(n: int) -> bytes:
    out = bytearray()
    n = int(n) & ((1 << 64) - 1)
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def put_field_varint(field: int, n: int) -> bytes:
    return put_varint((field << 3) | 0) + put_varint(n)


def put_field_bytes(field: int, data: bytes) -> bytes:
    return put_varint((field << 3) | 2) + put_varint(len(data)) + data


def put_field_str(field: int, text: str) -> bytes:
    return put_field_bytes(field, text.encode("utf-8"))
