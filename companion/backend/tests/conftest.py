"""共享 e2e 夹具：真实 HTTP 路由 + 临时库 + Mock LLM。

用法：测试函数声明参数 `api_client` 即得 TestClient；
`api_client.captured["messages"]` 是 Mock LLM 收到的消息，
`api_client.engine` 是临时库引擎，可用来查库。
"""
from __future__ import annotations

import json
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.models import Setting
from app.routers import characters as characters_router
from app.routers import chat as chat_router

MODULES_OFF = {
    "memory": False, "scenes": False, "rewrite": False, "keepsake": False,
    "tarot": False, "tavern": False, "codewatch": False, "touch": False,
    "harness": False, "glance": False, "live_douyin": False, "live": False,
    "play": False,
}


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'e2e.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    avatars = tmp_path / "avatars"
    avatars.mkdir()
    monkeypatch.setattr(characters_router, "AVATARS_DIR", avatars)
    from app.modules.character import exporter as exporter_module
    monkeypatch.setattr(exporter_module, "AVATARS_DIR", avatars)

    # chat 落库走 _persist 里的晚期 import，这里把真实引擎换掉
    import app.db as db_module
    monkeypatch.setattr(db_module, "engine", engine)

    # 假 coins 服务：不碰真实钱包文件
    fake_coins = types.ModuleType("app.services.coins")
    fake_coins.purse_line = lambda *a, **k: ""
    fake_coins.asks_purse = lambda *a, **k: False
    fake_coins.purse_say = lambda *a, **k: ""
    fake_coins.grant_talk = lambda *a, **k: None
    fake_coins.latest_wish_note = lambda *a, **k: ""
    sys.modules.setdefault("app.services.coins", fake_coins)
    # draw 服务整模块替换，避免拉重的依赖链
    fake_draw = types.ModuleType("app.modules.draw.service")
    fake_draw.realize_draws = lambda stream, *a, **k: stream
    sys.modules.setdefault("app.modules.draw.service", fake_draw)

    import app.modules.hooks as hooks_module
    monkeypatch.setattr(hooks_module, "schedule_after_reply", lambda *a, **k: None)
    import app.talk_log as talk_log_module
    monkeypatch.setattr(talk_log_module, "write", lambda *a, **k: None)

    captured: dict = {}

    import app.services.llm as llm_module

    async def fake_stream_chat(conf, messages):
        captured["messages"] = messages
        yield {"type": "text", "delta": "嗯。"}
        yield {"type": "done", "full_text": "嗯。"}

    monkeypatch.setattr(llm_module, "stream_chat", fake_stream_chat)

    import app.services.duplex as duplex_module

    async def fake_annotate(source, **kwargs):
        async for ev in source:
            yield ev

    monkeypatch.setattr(duplex_module, "annotate_stream", fake_annotate)

    with Session(engine) as s:
        s.add(Setting(key="modules", value=json.dumps(MODULES_OFF, ensure_ascii=False)))
        s.add(Setting(key="user_persona", value=json.dumps(
            {"enabled": True, "name": "阿黎", "description": "程序员，养了一只猫。"},
            ensure_ascii=False)))
        s.commit()

    app = FastAPI()
    app.include_router(characters_router.router)
    app.include_router(chat_router.router)

    def override_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as c:
        c.captured = captured
        c.engine = engine
        yield c
