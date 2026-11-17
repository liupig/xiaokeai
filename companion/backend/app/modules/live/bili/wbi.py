"""B 站网页接口的 WBI 参数签名。密钥只来自公开 nav 接口，不是账号密码。"""
from __future__ import annotations

import hashlib
import time
from urllib.parse import urlencode

# 文档公布的固定重排表。
_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)


def mixin_key(img_key: str, sub_key: str) -> str:
    raw = f"{img_key}{sub_key}"
    return "".join(raw[index] for index in _MIXIN_KEY_ENC_TAB)[:32]


def sign_params(params: dict, img_key: str, sub_key: str, *, timestamp: int | None = None) -> dict:
    signed = {key: value for key, value in params.items()}
    signed["wts"] = int(time.time()) if timestamp is None else int(timestamp)
    filtered = {
        key: "".join(char for char in str(value) if char not in "!'()*")
        for key, value in signed.items()
    }
    query = urlencode(sorted(filtered.items()))
    signed["w_rid"] = hashlib.md5((query + mixin_key(img_key, sub_key)).encode("utf-8")).hexdigest()
    return signed
