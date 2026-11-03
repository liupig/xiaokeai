"""开放平台回调签名。按文档：指定头按字典序拼接，接上 body 和密钥，MD5 再 base64。"""
from __future__ import annotations

import base64
import hashlib

_HEADER_KEYS = ("x-msg-type", "x-nonce-str", "x-roomid", "x-timestamp")


def callback_signature(headers: dict, body: str, secret: str) -> str:
    lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    pieces = [f"{key}={lowered.get(key, '')}" for key in _HEADER_KEYS if key in lowered]
    raw = ("".join([("&".join(pieces)), body or "", secret or ""])).encode("utf-8")
    return base64.b64encode(hashlib.md5(raw).digest()).decode("ascii")


def signature_ok(headers: dict, body: str, secret: str) -> bool:
    if not (secret or "").strip():
        return True
    got = str((headers or {}).get("x-signature") or (headers or {}).get("X-Signature") or "")
    if not got:
        lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        got = lowered.get("x-signature", "")
    return got == callback_signature(headers, body, secret)
