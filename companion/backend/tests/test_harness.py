"""dsh 接入：技能同步、现场摘要、哪一轮交给 harness。不启动真的 dsh。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.harness.brief import (  # noqa: E402
    TextGrowth, dance_opening, host_brief, turn_text, wants_harness, wish_recall,
)
from app.modules.harness.service import sync_skills  # noqa: E402


def test_user_talk_uses_harness_and_side_paths_do_not():
    assert wants_harness(enabled=True, mode="user")
    assert not wants_harness(enabled=False, mode="user")
    assert not wants_harness(enabled=True, mode="welcome")
    assert not wants_harness(enabled=True, mode="continue")
    assert not wants_harness(enabled=True, mode="user", reroll=True)
    assert not wants_harness(enabled=True, mode="user", afterglow=True)


def test_brief_keeps_persona_and_drops_the_director_manual():
    messages = [
        {"role": "system", "content": "你是清宵。"},
        {"role": "system", "content": "导演：[emo:happy] 然后 [dance:]"},
        {"role": "user", "content": "在吗"},
    ]
    brief = host_brief(messages, ["wave.vmd"])
    assert "清宵" in brief
    assert "wave.vmd" in brief
    assert "[dance:]" not in brief
    reading = host_brief(
        [{"role": "system", "content": "【当前扮演】临时看牌。\n【这一轮任务】只讲这一张。"}],
        ["wave.vmd"],
    )
    assert "wave.vmd" not in reading
    assert "只讲这一张" in reading


def test_a_heavy_session_gets_a_new_label():
    from app.modules.harness.service import session_label

    assert session_label(1, 0) == "xiaoke-1"
    assert session_label(1, 2) == "xiaoke-1-2"


def test_a_long_session_is_cut_before_the_kernel_fold():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from app.modules.harness import service

    assert service.should_cut(turns=None, generation=0, seeded=False) is False
    assert service.should_cut(turns=None, generation=0, seeded=True) is False
    assert service.should_cut(turns=None, generation=1, seeded=True) is True
    assert service.should_cut(turns=service.CUT_AFTER_TURNS - 1, generation=2, seeded=True) is False
    assert service.should_cut(turns=service.CUT_AFTER_TURNS, generation=2, seeded=True) is True

    root = Path(tempfile.mkdtemp())
    with patch.object(service, "home_dir", lambda: root):
        service._generation_path(1).parent.mkdir(parents=True, exist_ok=True)
        service._generation_path(1).write_text("1", encoding="utf-8")
        service.mark_seed(1)
        assert service.cut_session(1) == 2
        assert service.needs_seed(1)
        assert service._read_turns(1) == 0
        service.note_kept_turn(1)
        assert service._read_turns(1) == 1


def test_profile_patch_leaves_folding_to_the_host():
    import tempfile
    from pathlib import Path

    from app.modules.harness.service import sync_skills

    root = Path(tempfile.mkdtemp())
    sync_skills(root)
    text = (root / "profiles" / "sdk" / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "id: compaction-basic" in text
    assert "auto: false" in text
    assert "search: false" in text
    assert "fetch: false" in text
    assert "thresholdRatio" not in text
    assert "id: system-prompt" in text
    assert "调用 dance" in text
    assert "[draw:画面]" in text
    for name in ("chat", "tarot", "draw"):
        skill = (root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "disable-model-invocation: true" in skill
    dance = (root / "skills" / "dance" / "SKILL.md").read_text(encoding="utf-8")
    assert "disable-model-invocation" not in dance
    assert "再跳一次" in dance
    lookup = (root / "skills" / "lookup" / "SKILL.md").read_text(encoding="utf-8")
    assert "disable-model-invocation" not in lookup
    assert "[lookup:" in lookup
    assert "360" in lookup
    assert "百度" in lookup
    assert "心月狐 鸣潮" in lookup
    assert "不会替你改写" in lookup
    assert "调用 lookup" in text
    assert "心月狐 鸣潮" in text


def test_the_model_query_is_searched_as_written():
    from app.modules.websearch.service import accept_query

    assert accept_query("  心月狐 鸣潮 ") == "心月狐 鸣潮"
    assert accept_query("俄乌战争最新进展") == "俄乌战争最新进展"
    assert accept_query("茅台股价") == "茅台股价"
    assert accept_query("还有") == ""
    assert accept_query("最新") == ""
    assert accept_query("最新的状况") == "最新的状况"
    from app.modules.websearch.service import _off_title, _rescue_query, _stock_code

    assert _stock_code("https://quote.eastmoney.com/sh600519.html") == "sh600519"
    assert _stock_code("https://www.xueqiu.com/S/SZ002594") == "sz002594"
    assert _off_title("国家概况_中华人民共和国外交部")
    assert _off_title("俄 的意思, 俄 的解释")
    assert not _off_title("俄乌战争 第1661天")
    assert _rescue_query("俄乌战场最新情况") == "俄乌战争最新进展"
    assert _rescue_query("贵州茅台 股价") == ""


def test_search_merge_rotates_engines_and_drops_baidu_sogou():
    from app.modules.websearch.service import _rows, merge_rows

    merged = merge_rows([
        [("甲", "https://a.example/1"), ("乙", "https://www.baidu.com/s?wd=1")],
        [("丙", "https://b.example/2"), ("丁", "https://www.sogou.com/web")],
        [("甲二", "https://a.example/1"), ("戊", "https://c.example/3")],
    ])
    assert [title for title, _url in merged] == ["甲", "丙", "戊"]
    from app.modules.websearch.service import _public

    assert not _public("http://127.0.0.1/secret")
    assert not _public("http://192.168.1.1/")
    assert not _public("http://169.254.169.254/latest")
    assert _public("https://www.weather.com.cn/weather/1.shtml")
    page = '<h2><a href="https://www.weather.com.cn/weather/101010100.shtml">北京天气</a></h2>'
    assert _rows(page, r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>') == [
        ("北京天气", "https://www.weather.com.cn/weather/101010100.shtml")
    ]


def test_a_later_turn_keeps_only_recent_rounds():
    prior = []
    for i in range(15):
        prior.append({"role": "user", "content": f"问{i}"})
        prior.append({"role": "assistant", "content": f"答{i}"})
    text = turn_text(brief="", user_text="现在", prior=prior)
    assert "问4" not in text
    assert "问5" in text
    assert "答14" in text


def test_a_later_turn_still_hears_the_last_wish():
    note = wish_recall("[wish] 许愿池玩了2次。最近扔进了钥匙、信、手机，落下12枚金币。")
    assert "[wish]" not in note
    assert "落下12枚金币" in note
    text = turn_text(brief="", user_text="刚才扔了什么", recall=note)
    assert "【刚说过】" not in text
    assert "钥匙、信、手机" in text
    assert "刚才扔了什么" in text
    assert text.index("最近一次许愿") < text.index("【这句】")


def test_dance_opening_speaks_before_the_skill():
    assert dance_opening("跳个舞吧") == "好，我跳一支。"
    assert dance_opening("换一个") == ""
    prior = [{"role": "assistant", "content": "好呀[dance:soft-dance.vmd]"}]
    assert dance_opening("换一个", prior) == "好，换一支。"
    assert dance_opening("再跳一次", prior) == "好，再来一次。"
    text = turn_text(brief="", user_text="跳个舞吧", prior=None)
    assert "【这句】" in text
    assert "好，我跳一支。" in text
    assert "先调用 dance" in text


def test_turn_text_names_the_sections_the_skill_reads():
    text = turn_text(
        brief="名字：清宵",
        user_text="今天好累",
        prior=[{"role": "assistant", "content": "昨晚说到一半。"}],
    )
    assert "【刚说过】" in text
    assert "她：昨晚说到一半。" in text
    assert "【现场】" in text
    assert "【这句】" in text
    assert text.endswith("今天好累")


def test_growing_assistant_message_emits_only_the_new_tail():
    growth = TextGrowth()
    first = growth.feed({
        "id": "m1",
        "type": "assistant/message",
        "data": {"message": {"content": [{"type": "text", "text": "[emo:relaxed]在"}]}},
    })
    second = growth.feed({
        "id": "m1",
        "type": "assistant/message",
        "data": {"message": {"content": [{"type": "text", "text": "[emo:relaxed]在的"}]}},
    })
    assert first == "[emo:relaxed]在"
    assert second == "的"
    assert growth.finish("[emo:relaxed]在的") == ""


def test_streamed_chunks_are_not_repeated_by_the_final_message():
    growth = TextGrowth()
    assert growth.feed({
        "type": "assistant/chunk",
        "data": {"chunk": {"type": "reasoning-delta", "index": 0, "text": "先想一下"}},
    }) == ""
    first = growth.feed({
        "type": "assistant/chunk",
        "data": {"chunk": {"type": "text-delta", "index": 0, "text": "在的。"}},
    })
    second = growth.feed({
        "type": "assistant/chunk",
        "data": {"chunk": {"type": "text-delta", "index": 0, "text": "你呢？"}},
    })
    done = growth.feed({
        "id": "m1",
        "type": "assistant/message",
        "data": {"message": {"content": [{"type": "text", "text": "在的。你呢？"}]}},
    })
    assert first == "在的。"
    assert second == "你呢？"
    assert done == ""
    assert growth.finish("在的。你呢？") == ""


def test_skill_catalog_talk_is_not_spoken():
    from app.modules.harness.brief import SpokenGate

    gate = SpokenGate()
    leaked = gate.feed("哦，刚才的可用技能列表里没有chat了，现在可用的是dance、diagnose-windows-sandbox-acl、draw、tarot。")
    leaked += gate.feed("那用户现在说你在干嘛，不需要调用skill了。")
    kept = gate.feed("在的呀，正想你呢。")
    assert leaked == ""
    assert kept == "在的呀，正想你呢。"
    assert gate.flush() == ""


def test_volc_openai_base_becomes_the_messages_base():
    from app.modules.harness.service import messages_base

    assert messages_base("https://ark.cn-beijing.volces.com/api/v3") == (
        "https://ark.cn-beijing.volces.com/api/compatible"
    )
    assert messages_base("https://ark.cn-beijing.volces.com/api/coding/v3/") == (
        "https://ark.cn-beijing.volces.com/api/coding"
    )
    assert messages_base("https://ark.cn-beijing.volces.com/api/plan/v3") == (
        "https://ark.cn-beijing.volces.com/api/plan"
    )
    assert messages_base("https://ark.cn-beijing.volces.com/api/compatible") == (
        "https://ark.cn-beijing.volces.com/api/compatible"
    )
    assert messages_base("https://api.deepseek.com") == "https://api.deepseek.com/anthropic"
    assert messages_base("https://api.deepseek.com/anthropic") == (
        "https://api.deepseek.com/anthropic"
    )
    assert messages_base(None) is None
    assert messages_base("") is None


def test_thinking_off_reaches_dsh_as_reasoning_off():
    from app.modules.harness.service import reasoning_effort_for

    assert reasoning_effort_for("off") == "off"
    assert reasoning_effort_for("on") == "high"
    assert reasoning_effort_for("default") is None
    assert reasoning_effort_for(None) is None


def test_a_missing_session_is_not_an_already_open_one():
    from app.modules.harness.service import session_missing

    assert session_missing(RuntimeError('session "xiaoke-1" not found'))
    assert session_missing(RuntimeError('session "xiaoke-1" does not exist'))
    assert not session_missing(RuntimeError('session "xiaoke-1" already exists'))
    assert not session_missing(RuntimeError("the API key or AK/SK in the request is missing or invalid"))


def test_empty_dance_tag_is_a_stage_event_not_speech():
    from app.services.llm import TagStreamParser

    parser = TagStreamParser()
    events = parser.feed("[emo:happy][cam:full][dance:]")
    events += parser.flush()
    kinds = [(ev["type"], ev.get("value", ev.get("delta"))) for ev in events]
    assert ("emo", "happy") in kinds
    assert ("cam", "full") in kinds
    assert ("dance", "") in kinds
    looked = TagStreamParser().feed("我去查一下。[lookup:北京天气]")
    assert ("lookup", "北京天气") in [(ev["type"], ev.get("value")) for ev in looked]
    assert not any(ev["type"] == "text" and "dance" in (ev.get("delta") or "") for ev in events)


def test_draw_tag_is_a_picture_event_not_speech():
    from app.services.llm import TagStreamParser

    parser = TagStreamParser()
    events = parser.feed("[emo:happy]好，画给你看。")
    # 未写完的长标记先按住，不要拆成会念出来的字
    events += parser.feed("[draw:" + "雨" * 120)
    assert not any(ev["type"] == "text" and "draw" in (ev.get("delta") or "") for ev in events)
    events += parser.feed("]")
    events += parser.flush()
    assert ("draw", "雨" * 120) in [(ev["type"], ev.get("value")) for ev in events]
    assert any(ev["type"] == "text" and "画给你看" in (ev.get("delta") or "") for ev in events)


def test_a_concrete_draw_starts_from_the_users_words():
    from app.modules.draw.service import opening_line, user_draw_scene

    assert user_draw_scene("画一张我们相遇的时候的照片")
    assert user_draw_scene("画我和你在云南的场面")
    assert user_draw_scene("画我们在丽江的日子")
    assert user_draw_scene("再画一幅") == ""
    assert user_draw_scene("千军万马厮杀") == ""
    assert user_draw_scene("画得真好") == ""
    asked = [{"role": "assistant", "content": "好呀，你想画点什么呀？"}]
    assert user_draw_scene("高山草甸", asked) == "高山草甸"
    assert user_draw_scene("高山草甸") == ""
    assert opening_line("画我和你在云南的场面") == "好，我和你在云南的场面，我来画。"
    long = "画个图：THE BLACK TIDE — SORCERESS EMERGENCE " + "a cinematic still " * 20
    scene = user_draw_scene(long)
    assert scene.startswith("THE BLACK TIDE")
    assert len(scene) > 80
    assert opening_line(scene) == "好，我来画。"
    assert user_draw_scene("今天聊了很久" + "啊" * 90) == ""


def test_the_first_sentence_does_not_wait_for_the_model():
    import asyncio

    from app.modules.draw import service

    pulled = []

    async def model():
        pulled.append("model")
        yield {"type": "text", "delta": "后一句。"}
        yield {"type": "done", "full_text": "后一句。"}

    original = service.render_card
    service.render_card = lambda *args, **kwargs: {"url": "/k", "name": "云南"}

    async def run():
        kinds = []
        async for ev in service.realize_draws(model(), {}, user_text="画我和你在云南的场面"):
            kinds.append(ev["type"])
            if ev["type"] == "speech" and not pulled:
                kinds.append("spoke-before-model")
        return kinds

    try:
        kinds = asyncio.run(run())
    finally:
        service.render_card = original
    assert kinds[:3] == ["drawing", "text", "speech"]
    assert "spoke-before-model" in kinds


def test_bare_number_picks_the_spread_on_screen():
    from app.modules.tarot.plays import PLAYS, match_play_ordinal

    assert match_play_ordinal("5") == PLAYS[4]["id"]
    assert match_play_ordinal("第5个") == PLAYS[4]["id"]
    assert match_play_ordinal("开始呀") is None


def test_windows_process_cwd_leaves_the_e_drive(tmp_path: Path):
    from app.modules.harness.service import process_cwd
    folder = process_cwd(tmp_path)
    if folder is None:
        return
    assert Path(folder).drive.upper() in {"C:", "V:"}


def test_skill_file_syncs_into_an_isolated_home(tmp_path: Path):
    home = sync_skills(tmp_path)
    skill = home / "skills" / "chat" / "SKILL.md"
    assert skill.is_file()
    body = skill.read_text(encoding="utf-8")
    assert "name: chat" in body
    assert (home / "skills" / "dance" / "SKILL.md").is_file()
    assert (home / "skills" / "tarot" / "SKILL.md").is_file()
    assert (home / "skills" / "draw" / "SKILL.md").is_file()
    assert (home / "workspace").is_dir()
    skill.write_text("stale", encoding="utf-8")
    sync_skills(tmp_path)
    assert "name: chat" in skill.read_text(encoding="utf-8")


def test_the_wallet_number_is_not_a_sum_of_wishes():
    from app.services.coins import asks_purse, format_coins, purse_line, purse_say

    assert format_coins(4000) == "4"
    assert format_coins(1500) == "1.5"
    assert format_coins(100500) == "100"
    line = purse_line(19_000)
    assert "19" in line
    assert "不要把许愿落下的枚数加总" in line
    assert asks_purse("你知道我现在有多少钱吗？")
    assert asks_purse("我的所有金币是多少？")
    assert not asks_purse("茅台现在多少钱")
    assert not asks_purse("这次落下多少")
    assert purse_say(4_000) == "你现在有 4 枚金币。"


def test_draw_key_stays_on_volc():
    from app.modules.draw.service import draw_key

    volc = {"api_key": "ark-chat", "base_url": "https://ark.cn-beijing.volces.com/api/v3"}
    deepseek = {"api_key": "sk-deepseek", "base_url": "https://api.deepseek.com"}
    assert draw_key(volc, env={}) == "ark-chat"
    assert draw_key(deepseek, env={}) == ""
    assert draw_key(deepseek, env={"ARK_API_KEY": "ark-env"}) == "ark-env"
    assert draw_key({"api_key": "sk-other", "base_url": ""}, env={"VOLC_ARK_API_KEY": "ark-volc"}) == "ark-volc"


class _Proc:
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code


class _Client:
    def __init__(self, proc):
        self._proc = proc


class _Harness:
    def __init__(self, proc, initialized=True):
        self.client = _Client(proc)
        self._initialized = initialized
        self.closed = False

    def close(self):
        self.closed = True


class _TransportClosed(Exception):
    pass


_TransportClosed.__name__ = "TransportClosedError"


def test_a_dead_runtime_is_dropped_and_a_live_one_stays():
    from app.modules.harness.service import Runtime

    runtime = Runtime()
    dead = _Harness(_Proc(1))
    runtime._harness = dead
    runtime._open_ids.add("xiaoke-1")
    runtime.retire_if_dead()
    assert runtime._harness is None
    assert dead.closed
    assert runtime._open_ids == set()

    live = _Harness(_Proc(None))
    runtime._harness = live
    runtime._open_ids.add("xiaoke-1")
    runtime.retire_if_dead(RuntimeError("model said no"))
    assert runtime._harness is live
    assert not live.closed

    runtime.retire_if_dead(_TransportClosed("stdout closed"))
    assert runtime._harness is None
    assert live.closed
    assert runtime.running() is False
