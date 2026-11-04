from __future__ import annotations

import asyncio
import re

import httpx


RELEASE_URLS = (
    "https://gitee.com/hixiaokeai/xiaokeai/raw/master/release.json",
    "https://raw.githubusercontent.com/liupig/xiaokeai/master/release.json",
)


def validate_release(payload: object) -> dict:
    version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]{14}", version):
        raise ValueError("发布信息缺少有效的 14 位版本号")
    for key in ("notes", "downloads"):
        if key in payload and (
            not isinstance(payload[key], dict)
            or any(not isinstance(value, str) for value in payload[key].values())
        ):
            raise ValueError(f"发布信息的 {key} 字段无效")
    for key in ("published_at", "baidu_password"):
        if key in payload and not isinstance(payload[key], str):
            raise ValueError(f"发布信息的 {key} 字段无效")
    return payload


async def fetch_release(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    return validate_release(response.json())


async def fetch_first_release(client: httpx.AsyncClient, urls: tuple[str, ...] = RELEASE_URLS) -> dict:
    tasks = [asyncio.create_task(fetch_release(client, url)) for url in urls]
    last_error = None
    try:
        for task in asyncio.as_completed(tasks):
            try:
                return await task
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
        raise httpx.HTTPError("两个发布信息源均不可用") from last_error
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def with_update_status(release: dict, current_version: str | None) -> dict:
    return {
        **release,
        "update_available": current_version is None or release["version"] > current_version,
    }
