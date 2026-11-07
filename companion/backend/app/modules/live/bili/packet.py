"""哔哩哔哩开放平台长连接的二进制包。16 字节头，压缩包用 zlib。"""
from __future__ import annotations

import struct
import zlib

OP_HEARTBEAT = 2
OP_HEARTBEAT_REPLY = 3
OP_NOTIFY = 5
OP_AUTH = 7
OP_AUTH_REPLY = 8
PROTO_JSON = 0
PROTO_ZLIB = 2
_HEADER = 16
_MAX = 1_048_576


def pack_packet(op: int, body: bytes, proto: int = PROTO_JSON) -> bytes:
    payload = body or b""
    length = _HEADER + len(payload)
    return struct.pack(">IHHII", length, _HEADER, proto, int(op), 1) + payload


def unpack_packets(buf: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    packets: list[tuple[int, bytes]] = []
    view = buf or b""
    while len(view) >= _HEADER:
        length, header, proto, op, _seq = struct.unpack(">IHHII", view[:_HEADER])
        if header != _HEADER or length < _HEADER or length > _MAX:
            recovered = False
            for offset in range(1, len(view) - _HEADER + 1):
                next_length, next_header, _proto, _op, _seq = struct.unpack(
                    ">IHHII", view[offset:offset + _HEADER]
                )
                if next_header == _HEADER and _HEADER <= next_length <= _MAX:
                    view = view[offset:]
                    recovered = True
                    break
            if not recovered:
                return packets, b""
            continue
        if len(view) < length:
            break
        body = view[_HEADER:length]
        view = view[length:]
        if proto == PROTO_ZLIB:
            try:
                inner = zlib.decompress(body)
            except zlib.error:
                continue
            nested, _rest = unpack_packets(inner)
            packets.extend(nested)
            continue
        packets.append((int(op), body))
    return packets, view
