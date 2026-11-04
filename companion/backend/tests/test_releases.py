import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.services.releases import (
    RELEASE_URLS,
    fetch_first_release,
    validate_release,
    with_update_status,
)


def release(version: str) -> dict:
    return {
        "version": version,
        "notes": {"zh": "更新"},
        "downloads": {"baidu": "https://pan.baidu.com/example"},
    }


def fetch_with_transport(handler) -> dict:
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_first_release(client)

    return asyncio.run(run())


def test_first_valid_response_wins():
    async def handler(request: httpx.Request):
        if request.url.host == "gitee.com":
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=release("20261028135252"))
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=release("20261101000000"))

    assert fetch_with_transport(handler)["version"] == "20261101000000"


def test_invalid_fast_response_waits_for_other_source():
    async def handler(request: httpx.Request):
        if request.url.host == "gitee.com":
            await asyncio.sleep(0.02)
            return httpx.Response(200, json=release("20261028135252"))
        return httpx.Response(200, json={"version": "invalid"})

    assert fetch_with_transport(handler)["version"] == "20261028135252"


def test_http_failure_waits_for_other_source():
    async def handler(request: httpx.Request):
        if request.url.host == "gitee.com":
            await asyncio.sleep(0.02)
            return httpx.Response(200, json=release("20261028135252"))
        return httpx.Response(503)

    assert fetch_with_transport(handler)["version"] == "20261028135252"


def test_gitee_redirect_is_followed():
    async def handler(request: httpx.Request):
        if request.url.host == "gitee.com":
            return httpx.Response(
                302,
                headers={"location": "https://raw.giteeusercontent.com/release.json"},
            )
        if request.url.host == "raw.githubusercontent.com":
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=release("20261101000000"))
        return httpx.Response(200, json=release("20261028135252"))

    assert fetch_with_transport(handler)["version"] == "20261028135252"


def test_all_sources_failing_raises_http_error():
    def handler(request: httpx.Request):
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPError):
        fetch_with_transport(handler)


@pytest.mark.parametrize(
    ("current_version", "expected"),
    [(None, True), ("20261027120000", True), ("20261028135252", False), ("20261029120000", False)],
)
def test_update_status_uses_local_timestamp(current_version, expected):
    assert with_update_status(release("20261028135252"), current_version)["update_available"] is expected


def test_repository_release_file_is_valid():
    path = Path(__file__).resolve().parents[3] / "release.json"
    payload = validate_release(json.loads(path.read_text(encoding="utf-8")))
    assert set(payload["downloads"]) == {"baidu", "huggingface", "google_drive"}


def test_sources_point_to_master_release_file():
    assert len(RELEASE_URLS) == 2
    assert all(url.endswith("/master/release.json") for url in RELEASE_URLS)
