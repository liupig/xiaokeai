"""哔哩哔哩开放平台签名。文档要求的那一串 x-bili- 头，HMAC-SHA256。"""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid


def content_md5(body: bytes) -> str:
    return hashlib.md5(body or b"").hexdigest()


def signed_headers(access_key_id: str, access_key_secret: str, body: bytes,
                   *, nonce: str = "", timestamp: str = "") -> dict[str, str]:
    headers = {
        "x-bili-accesskeyid": access_key_id,
        "x-bili-content-md5": content_md5(body),
        "x-bili-signature-method": "HMAC-SHA256",
        "x-bili-signature-nonce": nonce or uuid.uuid4().hex,
        "x-bili-signature-version": "1.0",
        "x-bili-timestamp": timestamp or str(int(time.time())),
    }
    canonical = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
    digest = hmac.new(access_key_secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["Authorization"] = digest
    headers["Accept"] = "application/json"
    headers["Content-Type"] = "application/json"
    return headers
